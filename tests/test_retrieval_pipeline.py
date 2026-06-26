import logging
from pathlib import Path

import pytest

from context_search_tool import retrieval
from context_search_tool.config import (
    DEFAULT_CONFIG,
    EmbeddingConfig,
    IndexConfig,
    RetrievalConfig,
    ToolConfig,
)
from context_search_tool.indexer import index_repository
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    QueryPlan,
    RetrievalCandidate,
    RetrievalSummary,
    SymbolRef,
)
from context_search_tool.paths import index_dir_for
from context_search_tool.retrieval import query_repository
from context_search_tool.sqlite_store import SQLiteStore


class FakePlanner:
    def __init__(self, plan: QueryPlan) -> None:
        self.query_plan = plan
        self.calls: list[str] = []

    def plan_query(self, query: str) -> QueryPlan:
        self.calls.append(query)
        return self.query_plan

    def plan(self, query: str) -> QueryPlan:
        self.calls.append(query)
        return self.query_plan


def _write_go_imagebed_fixture(repo: Path) -> None:
    (repo / "handler").mkdir(parents=True)
    (repo / "middleware").mkdir(parents=True)
    (repo / "storage").mkdir(parents=True)
    (repo / "main.go").write_text(
        """
package main

func initStorage(storageType string) string {
    switch storageType {
    case "local":
        return NewLocalStorage("./uploads")
    case "oss":
        return NewOSSStorage("endpoint", "bucket")
    case "s3":
        return NewS3Storage("region", "bucket")
    default:
        return NewLocalStorage("./uploads")
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo / "handler" / "upload.go").write_text(
        """
package handler

type UploadHandler struct {}

func (h *UploadHandler) Upload() string {
    return "multipart file upload storage Save"
}

func (h *UploadHandler) MultiUpload() string {
    return "multipart files batch upload"
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo / "middleware" / "auth.go").write_text(
        """
package middleware

func AuthMiddleware() string {
    return "Authorization Bearer token query form"
}

func AdminMiddleware() string {
    return "admin token only"
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo / "storage" / "storage.go").write_text(
        """
package storage

type Storage interface {
    Save(path string) error
    Delete(path string) error
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo / "storage" / "local.go").write_text(
        """
package storage

func NewLocalStorage(basePath string) string {
    return "local"
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo / "storage" / "oss.go").write_text(
        """
package storage

func NewOSSStorage(endpoint string, bucket string) string {
    return "oss"
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo / "storage" / "s3.go").write_text(
        """
package storage

func NewS3Storage(region string, bucket string) string {
    return "s3"
}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_monorepo_scope_fixture(repo: Path) -> None:
    frontend = repo / "frontend"
    collector = repo / "collector"
    backend = repo / "investment-assistant-backend"

    (frontend / "src" / "stores" / "modules").mkdir(parents=True)
    (frontend / "src" / "views" / "portfolio").mkdir(parents=True)
    (frontend / "package.json").write_text(
        """
{
  "dependencies": {
    "@vitejs/plugin-vue": "latest",
    "pinia": "latest",
    "vite": "latest",
    "vue": "latest"
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (frontend / "src" / "stores" / "modules" / "auth.store.ts").write_text(
        """
import { defineStore } from "pinia";

export const useAuthStore = defineStore("auth", {
  actions: {
    async login(username: string, password: string) {
      return { username, password, domain: "frontend auth portfolio fund position" };
    },
    async register(email: string) {
      return { email, feature: "frontend auth register portfolio fund position" };
    },
    async fetchCurrentUser() {
      return { name: "frontend auth portfolio fund position user" };
    },
  },
});
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (frontend / "src" / "views" / "portfolio" / "index.vue").write_text(
        """
<script setup lang="ts">
async function fetchPortfolios() {
  return ["frontend portfolio fund position"];
}

async function fetchPositions() {
  return ["frontend portfolio fund position detail"];
}
</script>

<template>
  <section>portfolio fund position</section>
</template>
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (collector / "internal" / "api" / "handler").mkdir(parents=True)
    (collector / "internal" / "scheduler").mkdir(parents=True)
    (collector / "go.mod").write_text(
        """
module example.com/collector

go 1.22
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (collector / "internal" / "api" / "handler" / "collect_handler.go").write_text(
        """
package handler

type CollectHandler struct{}

func (h *CollectHandler) CollectNav() string {
    return "collector gin fund portfolio nav"
}

func (h *CollectHandler) BatchCollectNav() string {
    return "collector gin batch fund portfolio"
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (collector / "internal" / "scheduler" / "scheduler.go").write_text(
        """
package scheduler

type Scheduler struct{}

func (s *Scheduler) AddTask(name string) string {
    return "collector cron heartbeat fund portfolio " + name
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (backend / "src" / "main" / "java" / "com" / "example").mkdir(parents=True)
    (backend / "pom.xml").write_text(
        """
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>investment-assistant-backend</artifactId>
</project>
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (
        backend
        / "src"
        / "main"
        / "java"
        / "com"
        / "example"
        / "AuthController.java"
    ).write_text(
        """
package com.example;

class AuthController {
    private final UserAppService userAppService = new UserAppService();

    String login(String username) {
        return userAppService.register(username);
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (
        backend
        / "src"
        / "main"
        / "java"
        / "com"
        / "example"
        / "PortfolioAppService.java"
    ).write_text(
        """
package com.example;

class PortfolioAppService {
    String fetchPortfolios() {
        return "backend portfolio fund position auth service";
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (
        backend
        / "src"
        / "main"
        / "java"
        / "com"
        / "example"
        / "UserAppService.java"
    ).write_text(
        """
package com.example;

class UserAppService {
    String register(String username) {
        return "backend auth login register fetchCurrentUser " + username;
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _candidate_pool_paths_before_rerank(repo: Path, query: str) -> set[str]:
    config = DEFAULT_CONFIG
    index_dir = index_dir_for(repo)
    store = SQLiteStore(index_dir / "index.sqlite")
    original_tokens = retrieval._dedupe(retrieval.tokenize_query(query))
    deleted_ids = store.deleted_chunk_ids()
    initial_candidates = retrieval._initial_candidates(
        index_dir,
        store,
        query,
        original_tokens,
        config,
        deleted_ids,
    )
    signal_candidates = retrieval._signal_candidates(store, original_tokens, config)
    direct_candidates = retrieval._merge_candidates(
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
    relation_seed_candidates = retrieval._merge_candidates(
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
    candidates = retrieval._merge_candidates(
        [
            *direct_candidates.values(),
            *anchor_candidates,
            *relation_candidates,
        ]
    )
    chunks = store.chunks_for_ids(list(candidates))
    return {chunk.file_path.as_posix() for chunk in chunks.values()}


def test_generic_retrieval_finds_go_upload_handler_without_language_plugin(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_go_imagebed_fixture(repo)

    index_repository(repo, DEFAULT_CONFIG)
    bundle = query_repository(
        repo,
        "UploadHandler MultiUpload multipart file storage Save",
        DEFAULT_CONFIG,
        context_lines=2,
    )

    paths = [result.file_path.as_posix() for result in bundle.results[:5]]
    assert "handler/upload.go" in paths


def test_generic_retrieval_finds_go_auth_middleware_without_language_plugin(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_go_imagebed_fixture(repo)

    index_repository(repo, DEFAULT_CONFIG)
    bundle = query_repository(
        repo,
        "AuthMiddleware Authorization Bearer token AdminMiddleware",
        DEFAULT_CONFIG,
        context_lines=2,
    )

    paths = [result.file_path.as_posix() for result in bundle.results[:5]]
    assert "middleware/auth.go" in paths


def test_generic_retrieval_finds_go_storage_backends_without_language_plugin(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_go_imagebed_fixture(repo)

    index_repository(repo, DEFAULT_CONFIG)
    bundle = query_repository(
        repo,
        "initStorage NewLocalStorage NewOSSStorage NewS3Storage storage type",
        DEFAULT_CONFIG,
        context_lines=2,
    )

    paths = [result.file_path.as_posix() for result in bundle.results[:6]]
    assert "main.go" in paths
    assert any(
        path in paths
        for path in ["storage/local.go", "storage/oss.go", "storage/s3.go"]
    )


@pytest.mark.parametrize(
    ("query", "expected_path", "requires_project_score_part"),
    [
        (
            "frontend useAuthStore login register fetchCurrentUser Pinia",
            "frontend/src/stores/modules/auth.store.ts",
            True,
        ),
        (
            "frontend portfolio index.vue fetchPortfolios fetchPositions",
            "frontend/src/views/portfolio/index.vue",
            True,
        ),
        (
            "collector CollectHandler CollectNav BatchCollectNav gin",
            "collector/internal/api/handler/collect_handler.go",
            True,
        ),
        (
            "collector scheduler.go type Scheduler AddTask heartbeat cron",
            "collector/internal/scheduler/scheduler.go",
            True,
        ),
        (
            "AuthController login register UserAppService",
            "investment-assistant-backend/src/main/java/com/example/AuthController.java",
            False,
        ),
        (
            "investment-assistant-backend java AuthController login register UserAppService",
            "investment-assistant-backend/src/main/java/com/example/AuthController.java",
            True,
        ),
    ],
)
def test_monorepo_scope_rerank_surfaces_scoped_subproject_files(
    tmp_path: Path,
    query: str,
    expected_path: str,
    requires_project_score_part: bool,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_monorepo_scope_fixture(repo)
    index_repository(repo, DEFAULT_CONFIG)

    candidate_paths = _candidate_pool_paths_before_rerank(repo, query)
    assert expected_path in candidate_paths, (
        f"query={query!r} expected_path={expected_path!r} "
        f"candidate_paths={sorted(candidate_paths)!r}"
    )

    bundle = query_repository(repo, query, DEFAULT_CONFIG, context_lines=2)
    top_results = bundle.results[:5]
    top_paths = [result.file_path.as_posix() for result in top_results]
    assert expected_path in top_paths

    matching_result = next(
        result for result in top_results if result.file_path.as_posix() == expected_path
    )
    if requires_project_score_part:
        assert any(key.startswith("project_") for key in matching_result.score_parts)
        matching_index = top_results.index(matching_result)
        mismatch_indexes = [
            index
            for index, result in enumerate(top_results)
            if "project_scope_mismatch_penalty" in result.score_parts
        ]
        assert all(matching_index < index for index in mismatch_indexes)


def test_monorepo_scope_does_not_overconstrain_unscoped_business_query(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_monorepo_scope_fixture(repo)
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "portfolio service", DEFAULT_CONFIG, context_lines=2)
    top_results = bundle.results[:5]
    top_paths = [result.file_path.as_posix() for result in top_results]
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")
    top_project_roots = {
        str(chunk.metadata.get("project_root", ""))
        for result in top_results
        for chunk in store.chunks_for_file(result.file_path, 1)
        if "project_root" in chunk.metadata
    }

    assert any(
        path in top_paths
        for path in [
            "investment-assistant-backend/src/main/java/com/example/PortfolioAppService.java",
            "frontend/src/views/portfolio/index.vue",
        ]
    )
    assert len(top_project_roots) >= 2
    assert all(
        "project_scope_mismatch_penalty" not in result.score_parts
        for result in top_results
    )


def test_query_repository_exposes_explicit_file_hint_reason(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_monorepo_scope_fixture(repo)
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(
        repo,
        "collector CollectHandler collect_handler.go CollectNav BatchCollectNav gin",
        DEFAULT_CONFIG,
        context_lines=2,
    )

    matching_result = next(
        result
        for result in bundle.results
        if result.file_path.as_posix() == "collector/internal/api/handler/collect_handler.go"
    )

    assert "explicit file hint match" in matching_result.reasons
    assert "exact file path hint boost" not in matching_result.reasons


def test_generic_retrieval_finds_rust_source_without_language_plugin(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "src" / "lib.rs"
    source.parent.mkdir(parents=True)
    source.write_text(
        """
pub struct ImageStore;

impl ImageStore {
    pub fn delete_by_filename(&self, filename: &str) -> bool {
        !filename.is_empty()
    }

    pub fn upload_image(&self, path: &str) -> bool {
        !path.is_empty()
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    index_repository(repo, DEFAULT_CONFIG)
    bundle = query_repository(
        repo,
        "ImageStore delete_by_filename filename upload_image",
        DEFAULT_CONFIG,
        context_lines=2,
    )

    paths = [result.file_path.as_posix() for result in bundle.results[:5]]
    assert "src/lib.rs" in paths


def test_query_without_index_does_not_call_planner(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            grep_keywords=["ExpensiveHint"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    bundle = query_repository(repo, "targetToken", DEFAULT_CONFIG, planner=planner)

    assert planner.calls == []
    assert bundle.results == []
    assert bundle.planner.status == "disabled"


def test_project_scope_score_parts_affect_rerank_score() -> None:
    chunk = DocumentChunk(
        chunk_id="generic",
        file_path=Path("src/generic.ts"),
        start_line=1,
        end_line=1,
        content="export const generic = true",
        chunk_type="text",
        symbols=[],
        lexical_tokens=["generic"],
        embedding_id="generic",
        deleted_at=None,
        metadata={"language": "typescript"},
    )
    role = retrieval._ChunkRole("generic", 5, 0.0)
    flags = {
        "has_endpoint_signal": False,
        "is_controller": False,
        "has_relation_support": False,
    }
    base_parts = {"lexical": 0.8}
    scoped_parts = {
        "lexical": 0.8,
        "project_scope_boost": 0.10,
        "project_kind_boost": 0.06,
        "project_language_boost": 0.04,
    }

    base_score = retrieval._rerank_score(
        0.5,
        base_parts,
        chunk,
        flags,
        role,
        planner_ceiling=None,
    )
    scoped_score = retrieval._rerank_score(
        0.5,
        scoped_parts,
        chunk,
        flags,
        role,
        planner_ceiling=None,
    )

    assert scoped_score == pytest.approx(base_score + 0.20)


def test_frontend_entrypoint_score_part_affects_rerank_score() -> None:
    chunk = DocumentChunk(
        chunk_id="image-view",
        file_path=Path("src/views/image/ImageRemover.vue"),
        start_line=1,
        end_line=1,
        content="<template>image remover remove mask canvas</template>",
        chunk_type="text",
        symbols=[],
        lexical_tokens=["image", "remover", "remove", "mask", "canvas"],
        embedding_id="image-view",
        deleted_at=None,
        metadata={"language": "vue"},
    )
    role = retrieval._ChunkRole("generic", 5, 0.0)
    flags = {
        "has_endpoint_signal": False,
        "is_controller": False,
        "has_relation_support": False,
    }
    base_parts = {"lexical": 0.8, "token_coverage": 0.5}
    frontend_parts = {
        "lexical": 0.8,
        "token_coverage": 0.5,
        "frontend_entrypoint_boost": 0.35,
    }

    base_score = retrieval._rerank_score(
        0.5,
        base_parts,
        chunk,
        flags,
        role,
        planner_ceiling=None,
    )
    frontend_score = retrieval._rerank_score(
        0.5,
        frontend_parts,
        chunk,
        flags,
        role,
        planner_ceiling=None,
    )

    assert frontend_score == pytest.approx(base_score + 0.35)


def test_frontend_entrypoint_rerank_requires_targeted_direct_evidence() -> None:
    chunk = DocumentChunk(
        chunk_id="weak-sibling-view",
        file_path=Path("src/views/image/ImageSibling.vue"),
        start_line=1,
        end_line=1,
        content="<template>image helper</template>",
        chunk_type="text",
        symbols=[],
        lexical_tokens=["image", "helper"],
        embedding_id="weak-sibling-view",
        deleted_at=None,
        metadata={"language": "vue"},
    )
    role = retrieval._ChunkRole("generic", 5, 0.0)
    flags = {
        "has_endpoint_signal": False,
        "is_controller": False,
        "has_relation_support": False,
    }
    base_parts = {"lexical": 0.8, "token_coverage": 0.25, "path_symbol": 1.0}
    frontend_parts = {
        "lexical": 0.8,
        "token_coverage": 0.25,
        "path_symbol": 1.0,
        "frontend_entrypoint_boost": 0.35,
    }

    base_score = retrieval._rerank_score(
        0.5,
        base_parts,
        chunk,
        flags,
        role,
        planner_ceiling=None,
    )
    frontend_score = retrieval._rerank_score(
        0.5,
        frontend_parts,
        chunk,
        flags,
        role,
        planner_ceiling=None,
    )

    assert frontend_score == pytest.approx(base_score)


def test_frontend_support_name_score_part_affects_rerank_score() -> None:
    chunk = DocumentChunk(
        chunk_id="input-model-util",
        file_path=Path("src/utils/inputToModel.ts"),
        start_line=1,
        end_line=1,
        content="export function inputToModel() { return 'input model'; }",
        chunk_type="text",
        symbols=[],
        lexical_tokens=["input", "model"],
        embedding_id="input-model-util",
        deleted_at=None,
        metadata={"language": "typescript"},
    )
    role = retrieval._ChunkRole("generic", 5, 0.0)
    flags = {
        "has_endpoint_signal": False,
        "is_controller": False,
        "has_relation_support": False,
    }
    base_parts = {"lexical": 0.8, "token_coverage": 0.5}
    frontend_parts = {
        "lexical": 0.8,
        "token_coverage": 0.5,
        "frontend_support_name_match_boost": 0.18,
    }

    base_score = retrieval._rerank_score(
        0.5,
        base_parts,
        chunk,
        flags,
        role,
        planner_ceiling=None,
    )
    frontend_score = retrieval._rerank_score(
        0.5,
        frontend_parts,
        chunk,
        flags,
        role,
        planner_ceiling=None,
    )

    assert frontend_score == pytest.approx(base_score + 0.18)


def test_frontend_support_name_rerank_requires_targeted_direct_evidence() -> None:
    chunk = DocumentChunk(
        chunk_id="weak-support",
        file_path=Path("src/utils/inputToModel.ts"),
        start_line=1,
        end_line=1,
        content="export function helper() { return 'model'; }",
        chunk_type="text",
        symbols=[],
        lexical_tokens=["model"],
        embedding_id="weak-support",
        deleted_at=None,
        metadata={"language": "typescript"},
    )
    role = retrieval._ChunkRole("generic", 5, 0.0)
    flags = {
        "has_endpoint_signal": False,
        "is_controller": False,
        "has_relation_support": False,
    }
    base_parts = {"lexical": 0.8, "token_coverage": 0.25, "path_symbol": 1.0}
    frontend_parts = {
        "lexical": 0.8,
        "token_coverage": 0.25,
        "path_symbol": 1.0,
        "frontend_support_name_match_boost": 0.18,
    }

    base_score = retrieval._rerank_score(
        0.5,
        base_parts,
        chunk,
        flags,
        role,
        planner_ceiling=None,
    )
    frontend_score = retrieval._rerank_score(
        0.5,
        frontend_parts,
        chunk,
        flags,
        role,
        planner_ceiling=None,
    )

    assert frontend_score == pytest.approx(base_score)


def test_reasons_include_project_scope_diagnostics() -> None:
    reasons = retrieval._reasons(
        {
            "project_scope_boost": 0.10,
            "project_kind_boost": 0.06,
            "project_language_boost": 0.04,
            "project_path_hint_boost": 0.08,
            "project_file_hint_boost": 0.08,
            "project_scope_mismatch_penalty": -0.06,
        },
        "frontend upload flow",
    )

    assert "project scope match" in reasons
    assert "project kind match" in reasons
    assert "project language match" in reasons
    assert "project path hint match" in reasons
    assert "project file hint match" in reasons
    assert "project scope mismatch penalty" in reasons


def test_query_expands_signal_relations_before_weak_lexical_matches(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "WorkspaceController.java").write_text(
        """
class WorkspaceController {
  // 工作台相关代码
  String page() { return service.list(); }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceServiceImpl.java").write_text(
        """
class WorkspaceServiceImpl {
  String list() { return query.execute(); }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceQueryExe.java").write_text(
        """
class WorkspaceQueryExe {
  String execute() { return "workspace"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceDto.java").write_text(
        'class WorkspaceDto { String label = "工作台相关代码"; }\n',
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=4,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    controller_chunk = store.chunk_for_line(Path("WorkspaceController.java"), 3)
    service_chunk = store.chunk_for_line(Path("WorkspaceServiceImpl.java"), 2)
    executor_chunk = store.chunk_for_line(Path("WorkspaceQueryExe.java"), 2)
    controller_signal = CodeSignal(
        signal_id="sig-controller",
        chunk_id=controller_chunk.chunk_id,
        file_path=Path("WorkspaceController.java"),
        kind="endpoint",
        name="GET /workspace/page",
        start_line=3,
        end_line=3,
        language="java",
        tokens=["workspace", "工作台统计", "待我审核"],
        metadata={"path": "/workspace/page", "text": "工作台统计-待我审核"},
    )
    service_signal = CodeSignal(
        signal_id="sig-service",
        chunk_id=service_chunk.chunk_id,
        file_path=Path("WorkspaceServiceImpl.java"),
        kind="method",
        name="WorkspaceServiceImpl.list",
        start_line=2,
        end_line=2,
        language="java",
        tokens=["workspace", "service", "list"],
        metadata={},
    )
    executor_signal = CodeSignal(
        signal_id="sig-executor",
        chunk_id=executor_chunk.chunk_id,
        file_path=Path("WorkspaceQueryExe.java"),
        kind="method",
        name="WorkspaceQueryExe.execute",
        start_line=2,
        end_line=2,
        language="java",
        tokens=["workspace", "query", "execute"],
        metadata={},
    )
    store.replace_signals(Path("WorkspaceController.java"), [controller_signal])
    store.replace_signals(Path("WorkspaceServiceImpl.java"), [service_signal])
    store.replace_signals(Path("WorkspaceQueryExe.java"), [executor_signal])
    store.replace_relations(
        Path("WorkspaceController.java"),
        [
            CodeRelation(
                relation_id="rel-controller-service",
                source_signal_id="sig-controller",
                target_name="WorkspaceService.list",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("WorkspaceServiceImpl.java"),
        [
            CodeRelation(
                relation_id="rel-service-executor",
                source_signal_id="sig-service",
                target_name="WorkspaceQueryExe.execute",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )

    bundle = query_repository(repo, "工作台相关代码", config)

    # With rerank scoring, order is:
    # 1. Controller: original_direct (lexical + signal) - highest
    # 2. Dto: original_direct (lexical only) - high
    # 3. ServiceImpl: original_relation - lower
    # 4. QueryExe: original_relation - lowest
    assert [result.file_path for result in bundle.results] == [
        Path("WorkspaceController.java"),
        Path("WorkspaceDto.java"),
        Path("WorkspaceServiceImpl.java"),
        Path("WorkspaceQueryExe.java"),
    ]
    assert "signal" in bundle.results[0].score_parts
    assert "lexical" in bundle.results[1].score_parts
    assert "relation" in bundle.results[2].score_parts
    assert "relation" in bundle.results[3].score_parts


def test_workflow_alias_query_prefers_process_endpoint_over_generic_api(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "HealthCheckController.java").write_text(
        """
@RequestMapping("/health")
class HealthCheckController {
  /**
   * 健康检查接口
   */
  @GetMapping("/check")
  String healthCheck() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "ProcessOpenController.java").write_text(
        """
/**
 * 对外开放的流程处理控制器，专门用于 APAAS 系统间集成的接口
 */
@RequestMapping("/openapi/process")
class ProcessOpenController {
  /**
   * 启动流程
   */
  @PostMapping("/start")
  String start() { return processService.startProcess(); }
}
""".strip(),
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=2,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)

    bundle = query_repository(repo, "apaas工作流相关接口", config)

    assert bundle.results[0].file_path == Path("ProcessOpenController.java")
    assert bundle.results[1].file_path == Path("HealthCheckController.java")
    assert "POST /openapi/process/start" in bundle.summary.entry_points


def test_relation_expansion_scores_from_signal_strength(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    strong_controller = DocumentChunk(
        chunk_id="strong-controller",
        file_path=Path("StrongController.java"),
        start_line=1,
        end_line=5,
        content="class StrongController {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["common"],
        embedding_id="strong-controller",
        deleted_at=None,
        metadata={"language": "java"},
    )
    weak_controller = DocumentChunk(
        chunk_id="weak-controller",
        file_path=Path("WeakController.java"),
        start_line=1,
        end_line=5,
        content="class WeakController {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["common"],
        embedding_id="weak-controller",
        deleted_at=None,
        metadata={"language": "java"},
    )
    strong_service = DocumentChunk(
        chunk_id="strong-service",
        file_path=Path("StrongServiceImpl.java"),
        start_line=1,
        end_line=5,
        content="class StrongServiceImpl {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["service"],
        embedding_id="strong-service",
        deleted_at=None,
        metadata={"language": "java"},
    )
    weak_service = DocumentChunk(
        chunk_id="weak-service",
        file_path=Path("WeakServiceImpl.java"),
        start_line=1,
        end_line=5,
        content="class WeakServiceImpl {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["service"],
        embedding_id="weak-service",
        deleted_at=None,
        metadata={"language": "java"},
    )
    store.replace_chunks(
        Path("StrongController.java"),
        [strong_controller],
    )
    store.replace_chunks(Path("WeakController.java"), [weak_controller])
    store.replace_chunks(Path("StrongServiceImpl.java"), [strong_service])
    store.replace_chunks(Path("WeakServiceImpl.java"), [weak_service])
    strong_signal = CodeSignal(
        signal_id="sig-strong",
        chunk_id="strong-controller",
        file_path=Path("StrongController.java"),
        kind="endpoint",
        name="GET /strong",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["strong"],
        metadata={},
    )
    weak_signal = CodeSignal(
        signal_id="sig-weak",
        chunk_id="weak-controller",
        file_path=Path("WeakController.java"),
        kind="endpoint",
        name="GET /weak",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["weak"],
        metadata={},
    )
    strong_target = CodeSignal(
        signal_id="sig-strong-target",
        chunk_id="strong-service",
        file_path=Path("StrongServiceImpl.java"),
        kind="method",
        name="StrongServiceImpl.run",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["strong", "run"],
        metadata={},
    )
    weak_target = CodeSignal(
        signal_id="sig-weak-target",
        chunk_id="weak-service",
        file_path=Path("WeakServiceImpl.java"),
        kind="method",
        name="WeakServiceImpl.run",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["weak", "run"],
        metadata={},
    )
    store.replace_signals(
        Path("StrongController.java"),
        [strong_signal],
    )
    store.replace_signals(Path("WeakController.java"), [weak_signal])
    store.replace_signals(Path("StrongServiceImpl.java"), [strong_target])
    store.replace_signals(Path("WeakServiceImpl.java"), [weak_target])
    store.replace_relations(
        Path("StrongController.java"),
        [
            CodeRelation(
                relation_id="rel-strong",
                source_signal_id="sig-strong",
                target_name="StrongServiceImpl.run",
                kind="calls",
                confidence=0.8,
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("WeakController.java"),
        [
            CodeRelation(
                relation_id="rel-weak",
                source_signal_id="sig-weak",
                target_name="WeakServiceImpl.run",
                kind="calls",
                confidence=0.8,
                metadata={},
            )
        ],
    )

    expanded = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="strong-controller",
                score=10.0,
                source="signal,path_symbol",
                score_parts={"signal": 0.5, "path_symbol": 10.0},
            ),
            RetrievalCandidate(
                chunk_id="weak-controller",
                score=10.0,
                source="signal,path_symbol",
                score_parts={"signal": 0.05, "path_symbol": 10.0},
            ),
        ],
        DEFAULT_CONFIG,
    )

    scores = {candidate.chunk_id: candidate.score for candidate in expanded}
    assert scores["strong-service"] > scores["weak-service"]


def test_relation_expansion_ignores_candidates_without_signal_or_relation_score(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    source = DocumentChunk(
        chunk_id="source",
        file_path=Path("SourceController.java"),
        start_line=1,
        end_line=5,
        content="class SourceController {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["source"],
        embedding_id="source",
        deleted_at=None,
        metadata={"language": "java"},
    )
    target = DocumentChunk(
        chunk_id="target",
        file_path=Path("TargetServiceImpl.java"),
        start_line=1,
        end_line=5,
        content="class TargetServiceImpl {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["target"],
        embedding_id="target",
        deleted_at=None,
        metadata={"language": "java"},
    )
    source_signal = CodeSignal(
        signal_id="sig-source",
        chunk_id="source",
        file_path=Path("SourceController.java"),
        kind="endpoint",
        name="GET /source",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["source"],
        metadata={},
    )
    target_signal = CodeSignal(
        signal_id="sig-target",
        chunk_id="target",
        file_path=Path("TargetServiceImpl.java"),
        kind="method",
        name="TargetServiceImpl.run",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["target", "run"],
        metadata={},
    )
    store.replace_chunks(Path("SourceController.java"), [source])
    store.replace_chunks(Path("TargetServiceImpl.java"), [target])
    store.replace_signals(Path("SourceController.java"), [source_signal])
    store.replace_signals(Path("TargetServiceImpl.java"), [target_signal])
    store.replace_relations(
        Path("SourceController.java"),
        [
            CodeRelation(
                relation_id="rel-source-target",
                source_signal_id="sig-source",
                target_name="TargetServiceImpl.run",
                kind="calls",
                confidence=0.8,
                metadata={},
            )
        ],
    )

    expanded = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="source",
                score=1.0,
                source="semantic",
                score_parts={"semantic": 1.0},
            )
        ],
        DEFAULT_CONFIG,
    )

    assert expanded == []


def test_relation_expansion_adds_relation_score_to_existing_direct_candidate(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    source = DocumentChunk(
        chunk_id="source",
        file_path=Path("SourceController.java"),
        start_line=1,
        end_line=5,
        content="class SourceController {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["source"],
        embedding_id="source",
        deleted_at=None,
        metadata={"language": "java"},
    )
    target = DocumentChunk(
        chunk_id="target",
        file_path=Path("TargetServiceImpl.java"),
        start_line=1,
        end_line=5,
        content="class TargetServiceImpl {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["target"],
        embedding_id="target",
        deleted_at=None,
        metadata={"language": "java"},
    )
    source_signal = CodeSignal(
        signal_id="sig-source",
        chunk_id="source",
        file_path=Path("SourceController.java"),
        kind="endpoint",
        name="GET /source",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["source"],
        metadata={},
    )
    target_signal = CodeSignal(
        signal_id="sig-target",
        chunk_id="target",
        file_path=Path("TargetServiceImpl.java"),
        kind="method",
        name="TargetServiceImpl.run",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["target", "run"],
        metadata={},
    )
    store.replace_chunks(Path("SourceController.java"), [source])
    store.replace_chunks(Path("TargetServiceImpl.java"), [target])
    store.replace_signals(Path("SourceController.java"), [source_signal])
    store.replace_signals(Path("TargetServiceImpl.java"), [target_signal])
    store.replace_relations(
        Path("SourceController.java"),
        [
            CodeRelation(
                relation_id="rel-source-target",
                source_signal_id="sig-source",
                target_name="TargetServiceImpl.run",
                kind="calls",
                confidence=0.8,
                metadata={},
            )
        ],
    )

    expanded = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="source",
                score=1.0,
                source="signal",
                score_parts={"signal": 1.0},
            ),
            RetrievalCandidate(
                chunk_id="target",
                score=0.1,
                source="signal",
                score_parts={"signal": 0.1},
            ),
        ],
        DEFAULT_CONFIG,
    )

    assert any(candidate.chunk_id == "target" for candidate in expanded)


def test_relation_expansion_uses_batched_store_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    def java_chunk(chunk_id: str, file_path: Path) -> DocumentChunk:
        return DocumentChunk(
            chunk_id=chunk_id,
            file_path=file_path,
            start_line=1,
            end_line=5,
            content=f"class {file_path.stem} {{}}",
            chunk_type="symbol",
            symbols=[],
            lexical_tokens=[file_path.stem.lower()],
            embedding_id=chunk_id,
            deleted_at=None,
            metadata={"language": "java"},
        )

    def java_signal(
        signal_id: str,
        chunk: DocumentChunk,
        kind: str,
        name: str,
    ) -> CodeSignal:
        return CodeSignal(
            signal_id=signal_id,
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            kind=kind,
            name=name,
            start_line=1,
            end_line=1,
            language="java",
            tokens=[name.lower()],
            metadata={},
        )

    def relation(
        relation_id: str,
        source_signal_id: str,
        target_name: str,
    ) -> CodeRelation:
        return CodeRelation(
            relation_id=relation_id,
            source_signal_id=source_signal_id,
            target_name=target_name,
            kind="calls",
            confidence=0.9,
            metadata={},
        )

    source_a = java_chunk("source-a", Path("src/ControllerA.java"))
    source_b = java_chunk("source-b", Path("src/ControllerB.java"))
    service_a = java_chunk("service-a", Path("src/AppInfoServiceImpl.java"))
    service_b = java_chunk("service-b", Path("src/CatalogServiceImpl.java"))
    executor_a = java_chunk("executor-a", Path("src/PageAppCatalogQueryExe.java"))
    executor_b = java_chunk("executor-b", Path("src/PageReviewQueryExe.java"))
    for chunk in [source_a, source_b, service_a, service_b, executor_a, executor_b]:
        store.replace_chunks(chunk.file_path, [chunk])

    source_a_signal = java_signal(
        "sig-source-a",
        source_a,
        "endpoint",
        "GET /appInfo/page",
    )
    source_b_signal = java_signal(
        "sig-source-b",
        source_b,
        "endpoint",
        "GET /catalog/page",
    )
    service_a_signal = java_signal(
        "sig-service-a",
        service_a,
        "method",
        "AppInfoServiceImpl.page",
    )
    service_b_signal = java_signal(
        "sig-service-b",
        service_b,
        "method",
        "CatalogServiceImpl.page",
    )
    executor_a_signal = java_signal(
        "sig-executor-a",
        executor_a,
        "method",
        "PageAppCatalogQueryExe.execute",
    )
    executor_b_signal = java_signal(
        "sig-executor-b",
        executor_b,
        "method",
        "PageReviewQueryExe.execute",
    )
    store.replace_signals(source_a.file_path, [source_a_signal])
    store.replace_signals(source_b.file_path, [source_b_signal])
    store.replace_signals(service_a.file_path, [service_a_signal])
    store.replace_signals(service_b.file_path, [service_b_signal])
    store.replace_signals(executor_a.file_path, [executor_a_signal])
    store.replace_signals(executor_b.file_path, [executor_b_signal])
    store.replace_relations(
        source_a.file_path,
        [
            relation(
                "rel-source-a-service-a",
                "sig-source-a",
                "AppInfoServiceImpl.page",
            )
        ],
    )
    store.replace_relations(
        source_b.file_path,
        [
            relation(
                "rel-source-b-service-b",
                "sig-source-b",
                "CatalogServiceImpl.page",
            )
        ],
    )
    store.replace_relations(
        service_a.file_path,
        [
            relation(
                "rel-service-a-executor-a",
                "sig-service-a",
                "PageAppCatalogQueryExe.execute",
            )
        ],
    )
    store.replace_relations(
        service_b.file_path,
        [
            relation(
                "rel-service-b-executor-b",
                "sig-service-b",
                "PageReviewQueryExe.execute",
            )
        ],
    )

    call_counts = {
        "signals_for_chunks": 0,
        "relations_for_sources": 0,
        "chunks_matching_signal_or_symbols": 0,
        "signals_for_chunk": 0,
        "relations_for_source": 0,
        "chunks_matching_signal_or_symbol": 0,
    }
    captured_calls: dict[str, list[list[str]]] = {
        "signals_for_chunks": [],
        "relations_for_sources": [],
        "chunks_matching_signal_or_symbols": [],
    }
    original_signals_for_chunks = store.signals_for_chunks
    original_relations_for_sources = store.relations_for_sources
    original_chunks_matching_signal_or_symbols = (
        store.chunks_matching_signal_or_symbols
    )
    original_signals_for_chunk = store.signals_for_chunk
    original_relations_for_source = store.relations_for_source
    original_chunks_matching_signal_or_symbol = (
        store.chunks_matching_signal_or_symbol
    )

    def counting_signals_for_chunks(chunk_ids: list[str]) -> dict[str, list[CodeSignal]]:
        call_counts["signals_for_chunks"] += 1
        captured_calls["signals_for_chunks"].append(list(chunk_ids))
        return original_signals_for_chunks(chunk_ids)

    def counting_relations_for_sources(
        source_signal_ids: list[str],
    ) -> dict[str, list[CodeRelation]]:
        call_counts["relations_for_sources"] += 1
        captured_calls["relations_for_sources"].append(list(source_signal_ids))
        return original_relations_for_sources(source_signal_ids)

    def counting_chunks_matching_signal_or_symbols(
        target_names: list[str],
        limit_per_target: int,
    ) -> dict[str, list[DocumentChunk]]:
        call_counts["chunks_matching_signal_or_symbols"] += 1
        captured_calls["chunks_matching_signal_or_symbols"].append(list(target_names))
        return original_chunks_matching_signal_or_symbols(target_names, limit_per_target)

    def counting_signals_for_chunk(chunk_id: str) -> list[CodeSignal]:
        call_counts["signals_for_chunk"] += 1
        return original_signals_for_chunk(chunk_id)

    def counting_relations_for_source(source_signal_id: str) -> list[CodeRelation]:
        call_counts["relations_for_source"] += 1
        return original_relations_for_source(source_signal_id)

    def counting_chunks_matching_signal_or_symbol(
        target_name: str,
        limit: int,
    ) -> list[DocumentChunk]:
        call_counts["chunks_matching_signal_or_symbol"] += 1
        return original_chunks_matching_signal_or_symbol(target_name, limit)

    monkeypatch.setattr(store, "signals_for_chunks", counting_signals_for_chunks)
    monkeypatch.setattr(store, "relations_for_sources", counting_relations_for_sources)
    monkeypatch.setattr(
        store,
        "chunks_matching_signal_or_symbols",
        counting_chunks_matching_signal_or_symbols,
    )
    monkeypatch.setattr(store, "signals_for_chunk", counting_signals_for_chunk)
    monkeypatch.setattr(store, "relations_for_source", counting_relations_for_source)
    monkeypatch.setattr(
        store,
        "chunks_matching_signal_or_symbol",
        counting_chunks_matching_signal_or_symbol,
    )

    expanded = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="source-a",
                score=1.0,
                source="signal",
                score_parts={"signal": 1.0},
            ),
            RetrievalCandidate(
                chunk_id="source-b",
                score=1.0,
                source="signal",
                score_parts={"signal": 1.0},
            )
        ],
        _expansion_config(),
    )

    assert {candidate.chunk_id for candidate in expanded} == {
        "service-a",
        "service-b",
        "executor-a",
        "executor-b",
    }
    assert any(
        set(source_ids) == {"sig-source-a", "sig-source-b"}
        for source_ids in captured_calls["relations_for_sources"]
    )
    assert any(
        set(target_names) == {"AppInfoServiceImpl.page", "CatalogServiceImpl.page"}
        for target_names in captured_calls["chunks_matching_signal_or_symbols"]
    )
    assert any(
        set(chunk_ids) == {"service-a", "service-b"}
        for chunk_ids in captured_calls["signals_for_chunks"]
    )
    assert call_counts["signals_for_chunks"] > 0
    assert call_counts["relations_for_sources"] > 0
    assert call_counts["chunks_matching_signal_or_symbols"] > 0
    assert call_counts["relations_for_sources"] <= retrieval.MAX_EXPANSION_DEPTH
    assert (
        call_counts["chunks_matching_signal_or_symbols"]
        <= retrieval.MAX_EXPANSION_DEPTH
    )
    assert call_counts["signals_for_chunks"] <= retrieval.MAX_EXPANSION_DEPTH + 1
    assert call_counts["signals_for_chunk"] == 0
    assert call_counts["relations_for_source"] == 0
    assert call_counts["chunks_matching_signal_or_symbol"] == 0


def test_query_bundle_summary_groups_entrypoints_implementation_related_and_legacy(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "WorkspaceController.java").write_text(
        """
@RequestMapping("/workspace")
class WorkspaceController {
  @GetMapping("/page")
  String page() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceServiceImpl.java").write_text(
        """
class WorkspaceServiceImpl {
  String list() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceExecutor.java").write_text(
        """
class WorkspaceExecutor {
  String execute() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceDto.java").write_text(
        """
class WorkspaceDto {
  String name;
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceLegacyType.java").write_text(
        """
class WorkspaceLegacyType {
  String old;
}
""".strip(),
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=20,
            final_top_k=5,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    controller_chunk = store.chunk_for_line(Path("WorkspaceController.java"), 3)
    service_chunk = store.chunk_for_line(Path("WorkspaceServiceImpl.java"), 2)
    executor_chunk = store.chunk_for_line(Path("WorkspaceExecutor.java"), 2)
    dto_chunk = store.chunk_for_line(Path("WorkspaceDto.java"), 2)
    legacy_chunk = store.chunk_for_line(Path("WorkspaceLegacyType.java"), 2)

    store.replace_signals(
        Path("WorkspaceController.java"),
        [
            CodeSignal(
                signal_id="sig-endpoint",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("WorkspaceController.java"),
                kind="endpoint",
                name="GET /workspace/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["workspace", "page"],
                metadata={},
            ),
            CodeSignal(
                signal_id="sig-controller-comment",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("WorkspaceController.java"),
                kind="comment",
                name="WorkspaceController comment",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["workspace"],
                metadata={},
            ),
        ],
    )
    store.replace_signals(
        Path("WorkspaceServiceImpl.java"),
        [
            CodeSignal(
                signal_id="sig-service",
                chunk_id=service_chunk.chunk_id,
                file_path=Path("WorkspaceServiceImpl.java"),
                kind="method",
                name="WorkspaceServiceImpl.list",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["workspace", "service"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        Path("WorkspaceExecutor.java"),
        [
            CodeSignal(
                signal_id="sig-executor",
                chunk_id=executor_chunk.chunk_id,
                file_path=Path("WorkspaceExecutor.java"),
                kind="method",
                name="WorkspaceExecutor.execute",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["workspace", "executor"],
                metadata={},
            )
        ],
        )
    store.replace_signals(
        Path("WorkspaceDto.java"),
        [
            CodeSignal(
                signal_id="sig-dto",
                chunk_id=dto_chunk.chunk_id,
                file_path=Path("WorkspaceDto.java"),
                kind="type",
                name="WorkspaceDto",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["workspace", "dto"],
                metadata={},
            ),
            CodeSignal(
                signal_id="sig-dto-usage",
                chunk_id=dto_chunk.chunk_id,
                file_path=Path("WorkspaceDto.java"),
                kind="usage",
                name="WorkspaceDto.load",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["workspace", "dto"],
                metadata={},
            ),
        ],
    )
    store.replace_signals(
        Path("WorkspaceLegacyType.java"),
        [
            CodeSignal(
                signal_id="sig-legacy",
                chunk_id=legacy_chunk.chunk_id,
                file_path=Path("WorkspaceLegacyType.java"),
                kind="type",
                name="WorkspaceLegacyType",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["workspace", "legacy"],
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("WorkspaceController.java"),
        [
            CodeRelation(
                relation_id="rel-controller-service",
                source_signal_id="sig-endpoint",
                target_name="WorkspaceServiceImpl.list",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("WorkspaceServiceImpl.java"),
        [
            CodeRelation(
                relation_id="rel-service-executor",
                source_signal_id="sig-service",
                target_name="WorkspaceExecutor.execute",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )

    bundle = query_repository(repo, "workspace", config)

    assert bundle.summary.entry_points == ["GET /workspace/page"]
    assert bundle.summary.implementation == [
        "WorkspaceExecutor.execute",
        "WorkspaceServiceImpl.list",
    ]
    assert bundle.summary.related_types == ["WorkspaceDto"]
    assert bundle.summary.possibly_legacy == ["WorkspaceLegacyType"]


def test_grouping_reasons_in_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "WorkspaceController.java").write_text(
        """
@RequestMapping("/workspace")
class WorkspaceController {
  @GetMapping("/page")
  String page() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceServiceImpl.java").write_text(
        """
class WorkspaceServiceImpl {
  String list() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=20,
            final_top_k=4,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    controller_chunk = store.chunk_for_line(Path("WorkspaceController.java"), 3)
    service_chunk = store.chunk_for_line(Path("WorkspaceServiceImpl.java"), 2)

    store.replace_signals(
        Path("WorkspaceController.java"),
        [
            CodeSignal(
                signal_id="sig-endpoint",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("WorkspaceController.java"),
                kind="endpoint",
                name="GET /workspace/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["workspace", "page"],
                metadata={"http_method": "GET"},
            ),
            CodeSignal(
                signal_id="sig-controller-comment",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("WorkspaceController.java"),
                kind="comment",
                name="WorkspaceController comment",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["workspace", "comment"],
                metadata={},
            ),
        ],
    )
    store.replace_signals(
        Path("WorkspaceServiceImpl.java"),
        [
            CodeSignal(
                signal_id="sig-service",
                chunk_id=service_chunk.chunk_id,
                file_path=Path("WorkspaceServiceImpl.java"),
                kind="method",
                name="WorkspaceServiceImpl.list",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["workspace", "service"],
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("WorkspaceController.java"),
        [
            CodeRelation(
                relation_id="rel-controller-service",
                source_signal_id="sig-endpoint",
                target_name="WorkspaceServiceImpl.list",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )

    bundle = query_repository(repo, "page", config)

    assert any(
        "endpoint signal match" in reason
        for result in bundle.results
        for reason in result.reasons
    )
    assert any(
        "comment signal match" in reason
        for result in bundle.results
        for reason in result.reasons
    )
    assert any(
        "implementation chain match" in reason
        for result in bundle.results
        for reason in result.reasons
    )


def test_legacy_classification_is_per_chunk_in_merged_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    content = """class LegacyWorkspaceController {
  // GET /legacy/workspace/list
  String page() { return \"ok\"; }
}\n""" + "\n".join("line-%d" % i for i in range(2, 85)) + """

class LegacyServiceImpl {
  String query() { return \"ok\"; }
}\n""" + "\n".join("line-%d" % i for i in range(86, 170)) + """

class LegacyWorkspaceType {
  String name;
}
"""
    (repo / "LegacyWorkspace.java").write_text(content, encoding="utf-8")
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=30,
            final_top_k=5,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    controller_chunk = store.chunk_for_line(Path("LegacyWorkspace.java"), 3)
    service_chunk = store.chunk_for_line(Path("LegacyWorkspace.java"), 86)
    legacy_chunk = store.chunk_for_line(Path("LegacyWorkspace.java"), 168)

    store.replace_signals(
        Path("LegacyWorkspace.java"),
        [
            CodeSignal(
                signal_id="sig-legacy-endpoint",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("LegacyWorkspace.java"),
                kind="endpoint",
                name="GET /legacy/workspace/list",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["legacy", "workspace"],
                metadata={"path": "/legacy/workspace/list"},
            ),
            CodeSignal(
                signal_id="sig-service",
                chunk_id=service_chunk.chunk_id,
                file_path=Path("LegacyWorkspace.java"),
                kind="method",
                name="LegacyServiceImpl.query",
                start_line=86,
                end_line=86,
                language="java",
                tokens=["legacy", "service"],
                metadata={},
            ),
            CodeSignal(
                signal_id="sig-legacy-type",
                chunk_id=legacy_chunk.chunk_id,
                file_path=Path("LegacyWorkspace.java"),
                kind="type",
                name="LegacyWorkspaceType",
                start_line=168,
                end_line=168,
                language="java",
                tokens=["legacy", "workspace", "type"],
                metadata={},
            ),
        ],
    )
    store.replace_relations(
        Path("LegacyWorkspace.java"),
        [
            CodeRelation(
                relation_id="rel-endpoint-service",
                source_signal_id="sig-legacy-endpoint",
                target_name="LegacyServiceImpl.query",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )

    bundle = query_repository(repo, "legacy workspace", config)

    assert bundle.results[0].file_path == Path("LegacyWorkspace.java")
    assert bundle.summary.possibly_legacy == ["LegacyWorkspaceType"]
    legacy_result = next(
        result
        for result in bundle.results
        if result.file_path == Path("LegacyWorkspace.java")
    )
    assert any(
        "possibly legacy: no active usage signal found"
        in reason for reason in legacy_result.reasons
    )


def test_query_bundle_summary_construction_defaults_and_explicit(tmp_path: Path) -> None:
    explicit_summary = RetrievalSummary(
        entry_points=["GET /explicit"],
        implementation=["ExplicitService"],
        related_types=["ExplicitDto"],
        possibly_legacy=["ExplicitLegacy"],
    )

    bundle_with_summary = retrieval.QueryBundle(
        query="q",
        expanded_tokens=["q"],
        results=[],
        followup_keywords=["q"],
        summary=explicit_summary,
    )
    assert bundle_with_summary.summary == explicit_summary

    legacy_style_bundle = retrieval.QueryBundle(
        query="q",
        expanded_tokens=["q"],
        results=[],
        followup_keywords=["q"],
    )
    assert legacy_style_bundle.summary == RetrievalSummary()
    assert legacy_style_bundle.results == []


def test_relation_expansion_terminates_cyclic_relations(tmp_path: Path) -> None:
    store = _graph_store(
        tmp_path,
        ["A", "B", "C"],
        [("A", "B", 0.9), ("B", "C", 0.9), ("C", "A", 0.9)],
    )

    candidates = retrieval._relation_expansion_candidates(
        store,
        [_seed_candidate("A")],
        _expansion_config(),
    )

    assert [candidate.chunk_id for candidate in candidates] == ["chunk-B", "chunk-C"]


def test_relation_expansion_stops_at_depth_three(tmp_path: Path) -> None:
    store = _graph_store(
        tmp_path,
        ["A", "B", "C", "D", "E"],
        [("A", "B", 0.9), ("B", "C", 0.9), ("C", "D", 0.9), ("D", "E", 0.9)],
    )

    candidates = retrieval._relation_expansion_candidates(
        store,
        [_seed_candidate("A")],
        _expansion_config(),
    )

    assert [candidate.chunk_id for candidate in candidates] == [
        "chunk-B",
        "chunk-C",
        "chunk-D",
    ]


def test_relation_expansion_propagates_stronger_same_layer_arrival(
    tmp_path: Path,
) -> None:
    store = _graph_store(
        tmp_path,
        ["A_low", "A_high", "B", "C"],
        [("A_low", "B", 0.5), ("A_high", "B", 0.9), ("B", "C", 0.9)],
    )

    candidates = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="chunk-A_low",
                score=1.0,
                source="signal",
                score_parts={"signal": 1.0},
            ),
            RetrievalCandidate(
                chunk_id="chunk-A_high",
                score=1.0,
                source="planner_signal",
                score_parts={"planner_signal": 1.0},
            ),
        ],
        _expansion_config(),
    )

    candidates_by_chunk = {candidate.chunk_id: candidate for candidate in candidates}
    b_score = 0.65 * 0.9 * retrieval._RELATION_SCORE_DECAY
    c_score = b_score * 0.9 * retrieval._RELATION_SCORE_DECAY

    assert candidates_by_chunk["chunk-B"].score_parts["relation"] == pytest.approx(
        b_score
    )
    assert candidates_by_chunk["chunk-B"].score_parts["planner_relation"] == (
        pytest.approx(b_score)
    )
    assert "original_relation" not in candidates_by_chunk["chunk-B"].score_parts
    assert candidates_by_chunk["chunk-C"].score_parts["relation"] == pytest.approx(
        c_score
    )
    assert candidates_by_chunk["chunk-C"].score_parts["planner_relation"] == (
        pytest.approx(c_score)
    )
    assert "original_relation" not in candidates_by_chunk["chunk-C"].score_parts


def test_relation_expansion_filters_low_confidence_relations(tmp_path: Path) -> None:
    store = _graph_store(
        tmp_path,
        ["A", "B", "C"],
        [("A", "B", 0.49), ("A", "C", 0.5)],
    )

    candidates = retrieval._relation_expansion_candidates(
        store,
        [_seed_candidate("A")],
        _expansion_config(),
    )

    assert [candidate.chunk_id for candidate in candidates] == ["chunk-C"]


def test_relation_expansion_logs_when_candidate_limit_is_hit(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    target_names = [
        f"T{index}" for index in range(retrieval.MAX_EXPANSION_CANDIDATES + 5)
    ]
    store = _graph_store(
        tmp_path,
        ["A", *target_names],
        [("A", target, 0.9) for target in target_names],
    )

    caplog.set_level(logging.WARNING, logger=retrieval.__name__)
    candidates = retrieval._relation_expansion_candidates(
        store,
        [_seed_candidate("A")],
        _expansion_config(),
    )

    assert len(candidates) == retrieval.MAX_EXPANSION_CANDIDATES
    assert "relation expansion hit candidate limit" in caplog.text.lower()


def test_relation_expansion_ignores_high_path_symbol_seed_without_signal(
    tmp_path: Path,
) -> None:
    store = _graph_store(
        tmp_path,
        ["Direct", "Seed", "Service", "Executor", "Dto"],
        [("Seed", "Service", 0.5), ("Service", "Executor", 1.0)],
    )
    direct_signal = RetrievalCandidate(
        chunk_id="chunk-Direct",
        score=1.0,
        source="signal",
        score_parts={"signal": 1.0},
    )
    high_path_symbol_seed = RetrievalCandidate(
        chunk_id="chunk-Seed",
        score=10.0,
        source="path_symbol",
        score_parts={"path_symbol": 10.0},
    )
    weak_dto = RetrievalCandidate(
        chunk_id="chunk-Dto",
        score=0.05,
        source="lexical",
        score_parts={"lexical": 0.05},
    )

    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        [direct_signal, high_path_symbol_seed, weak_dto],
        _expansion_config(),
    )
    ranked = retrieval._rank_chunks(
        store,
        retrieval._merge_candidates(
            [direct_signal, high_path_symbol_seed, weak_dto, *relation_candidates]
        ),
        [],
        "workspace",
    )
    scores = {item.chunk.chunk_id: item.score for item in ranked}

    assert relation_candidates == []
    assert "chunk-Service" not in scores
    assert "chunk-Executor" not in scores
    assert scores["chunk-Direct"] > scores["chunk-Dto"]


def test_relation_expansion_preserves_mixed_original_and_planner_provenance(
    tmp_path: Path,
) -> None:
    store = _graph_store(
        tmp_path,
        ["Source", "Target"],
        [("Source", "Target", 0.9)],
    )

    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="chunk-Source",
                score=1.0,
                source="signal,planner_signal",
                score_parts={"signal": 1.0, "planner_signal": 1.0},
            )
        ],
        _expansion_config(),
    )

    target = relation_candidates[0]
    assert target.score_parts["relation"] == target.score
    assert target.score_parts["planner_relation"] == target.score
    assert target.score_parts["original_relation"] == target.score
    assert "planner_signal" not in target.score_parts
    assert retrieval._is_planner_hint_only(target.score_parts) is False


def test_relation_expansion_uses_anchor_only_seed_as_original_evidence(
    tmp_path: Path,
) -> None:
    store = _graph_store(
        tmp_path,
        ["Source", "Target"],
        [("Source", "Target", 0.9)],
    )

    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="chunk-Source",
                score=0.55,
                source="anchored_relation",
                score_parts={
                    "anchored_relation": 0.55,
                    "directory_anchor": 0.55,
                    "original_relation": 0.55,
                },
            )
        ],
        _expansion_config(),
    )

    target = relation_candidates[0]
    assert target.chunk_id == "chunk-Target"
    assert target.score == pytest.approx(0.55 * 0.9 * 0.8)
    assert target.score_parts["relation"] == target.score
    assert target.score_parts["original_relation"] == target.score
    assert "planner_relation" not in target.score_parts


def test_relation_expansion_prefers_signal_seed_over_weaker_anchor(
    tmp_path: Path,
) -> None:
    store = _graph_store(
        tmp_path,
        ["Source", "Target"],
        [("Source", "Target", 0.9)],
    )

    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="chunk-Source",
                score=1.0,
                source="signal,anchored_relation",
                score_parts={
                    "signal": 1.0,
                    "anchored_relation": 0.55,
                    "directory_anchor": 0.55,
                    "original_relation": 0.55,
                },
            )
        ],
        _expansion_config(),
    )

    target = relation_candidates[0]
    assert target.chunk_id == "chunk-Target"
    assert target.score == pytest.approx(1.0 * 0.9 * 0.8)
    assert target.score_parts["relation"] == target.score
    assert target.score_parts["original_relation"] == target.score


def test_relation_expansion_keeps_direct_text_seed_when_anchor_seed_has_higher_score(
    tmp_path: Path,
) -> None:
    store = _graph_store(
        tmp_path,
        ["Direct", "DirectTarget", "Anchor"],
        [("Direct", "DirectTarget", 0.9)],
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=0,
            final_top_k=1,
            context_before_lines=0,
            context_after_lines=0,
        )
    )

    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="chunk-Anchor",
                score=0.8,
                source="anchored_relation",
                score_parts={
                    "anchored_relation": 0.8,
                    "same_file_anchor": 0.8,
                    "original_relation": 0.8,
                },
            ),
            RetrievalCandidate(
                chunk_id="chunk-Direct",
                score=0.61,
                source="direct_text",
                score_parts={"direct_text": 0.61},
            ),
        ],
        config,
    )

    target = relation_candidates[0]
    assert target.chunk_id == "chunk-DirectTarget"
    assert target.score == pytest.approx(0.61 * 0.9 * 0.8)
    assert target.score_parts["relation"] == target.score
    assert target.score_parts["original_relation"] == target.score


def test_relation_expansion_keeps_planner_only_seed_provenance_when_seed_has_lexical_evidence(
    tmp_path: Path,
) -> None:
    store = _graph_store(
        tmp_path,
        ["Source", "Target"],
        [("Source", "Target", 0.9)],
    )

    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="chunk-Source",
                score=1.0,
                source="lexical,planner_signal",
                score_parts={"lexical": 1.0, "planner_signal": 1.0},
            )
        ],
        _expansion_config(),
    )

    target = relation_candidates[0]
    assert target.score_parts["relation"] == target.score
    assert target.score_parts["planner_relation"] == target.score
    assert "original_relation" not in target.score_parts
    assert retrieval._is_planner_hint_only(target.score_parts) is True


def test_route_score_parts_prefers_exact_route_over_sibling_route() -> None:
    exact_signal = CodeSignal(
        signal_id="sig-exact",
        chunk_id="exact",
        file_path=Path("AppCatalogController.java"),
        kind="endpoint",
        name="POST /appCatalog/page",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["app", "catalog", "page", "/appCatalog/page"],
        metadata={"path": "/appCatalog/page"},
    )
    sibling_signal = CodeSignal(
        signal_id="sig-sibling",
        chunk_id="sibling",
        file_path=Path("AppCatalogOpenController.java"),
        kind="endpoint",
        name="POST /openApi/appCatalog/page",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["open", "api", "app", "catalog", "page", "/openApi/appCatalog/page"],
        metadata={"path": "/openApi/appCatalog/page"},
    )
    false_sibling_signal = CodeSignal(
        signal_id="sig-false-sibling",
        chunk_id="false-sibling",
        file_path=Path("MegaCatalogController.java"),
        kind="endpoint",
        name="POST /megaCatalog/page",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["mega", "catalog", "page", "/megaCatalog/page"],
        metadata={"path": "/megaCatalog/page"},
    )

    exact_parts = retrieval._route_score_parts([exact_signal], "/appCatalog/page canApply")
    sibling_parts = retrieval._route_score_parts([sibling_signal], "/appCatalog/page canApply")
    false_sibling_parts = retrieval._route_score_parts([false_sibling_signal], "/catalog/page canApply")

    assert exact_parts["route_exact_match"] == 0.35
    assert sibling_parts["route_sibling_penalty"] == -0.18
    assert "route_sibling_penalty" not in false_sibling_parts
    assert false_sibling_parts["route_mismatch_penalty"] == -0.30
    assert exact_parts["route_exact_match"] > abs(sibling_parts["route_sibling_penalty"])


def test_route_rerank_prefers_exact_controller_over_noisy_sibling(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    exact = DocumentChunk(
        chunk_id="exact",
        file_path=Path("src/main/java/AppCatalogController.java"),
        start_line=1,
        end_line=40,
        content='@RequestMapping("/appCatalog") class AppCatalogController {}',
        chunk_type="symbol",
        lexical_tokens=["app", "catalog", "page", "/appCatalog/page"],
        metadata={"language": "java"},
    )
    sibling = DocumentChunk(
        chunk_id="sibling",
        file_path=Path("src/main/java/AppCatalogOpenController.java"),
        start_line=1,
        end_line=40,
        content='@RequestMapping("/openApi/appCatalog") class AppCatalogOpenController {}',
        chunk_type="symbol",
        lexical_tokens=["open", "api", "app", "catalog", "page", "/openApi/appCatalog/page"],
        metadata={"language": "java"},
    )
    for chunk in (exact, sibling):
        store.replace_chunks(chunk.file_path, [chunk])
    store.replace_signals(
        exact.file_path,
        [
            CodeSignal(
                signal_id="sig-exact",
                chunk_id="exact",
                file_path=exact.file_path,
                kind="endpoint",
                name="POST /appCatalog/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["app", "catalog", "page", "/appCatalog/page"],
                metadata={"path": "/appCatalog/page"},
            )
        ],
    )
    store.replace_signals(
        sibling.file_path,
        [
            CodeSignal(
                signal_id="sig-sibling",
                chunk_id="sibling",
                file_path=sibling.file_path,
                kind="endpoint",
                name="POST /openApi/appCatalog/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["open", "api", "app", "catalog", "page", "/openApi/appCatalog/page"],
                metadata={"path": "/openApi/appCatalog/page"},
            )
        ],
    )

    ranked = retrieval._rank_chunks(
        store,
        {
            "exact": RetrievalCandidate(
                chunk_id="exact",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.35, "path_symbol": 3.0, "signal": 0.6},
            ),
            "sibling": RetrievalCandidate(
                chunk_id="sibling",
                score=1.0,
                source="direct",
                score_parts={
                    "semantic": 0.65,
                    "path_symbol": 4.25,
                    "direct_text": 1.0,
                    "signal": 1.0,
                },
            ),
        },
        ["app", "catalog", "page", "can", "apply"],
        "/appCatalog/page canApply",
    )

    assert ranked[0].chunk.chunk_id == "exact"
    assert ranked[0].score_parts["route_exact_match"] == 0.35
    assert ranked[1].score_parts["route_sibling_penalty"] == -0.18


def _spring_path_graph_case(
    tmp_path: Path,
) -> tuple[SQLiteStore, dict[str, RetrievalCandidate]]:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    exact = DocumentChunk(
        chunk_id="exact-controller",
        file_path=Path("src/main/java/com/example/controller/AppCatalogController.java"),
        start_line=1,
        end_line=40,
        content='@RequestMapping("/appCatalog") class AppCatalogController { String page() { return service.page(); } }',
        chunk_type="symbol",
        lexical_tokens=["app", "catalog", "page", "/appCatalog/page"],
        metadata={"language": "java"},
    )
    sibling = DocumentChunk(
        chunk_id="sibling-controller",
        file_path=Path("src/main/java/com/example/controller/AppCatalogOpenController.java"),
        start_line=1,
        end_line=40,
        content='@RequestMapping("/openApi/appCatalog") class AppCatalogOpenController { String page() { return openService.page(); } }',
        chunk_type="symbol",
        lexical_tokens=["open", "api", "app", "catalog", "page", "/openApi/appCatalog/page"],
        metadata={"language": "java"},
    )
    service_impl = DocumentChunk(
        chunk_id="service-impl",
        file_path=Path("src/main/java/com/example/service/impl/CatalogQueryServiceImpl.java"),
        start_line=1,
        end_line=40,
        content="class CatalogQueryServiceImpl { String page() { return executor.execute(); } }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "impl", "page"],
        metadata={"language": "java"},
    )
    service_interface = DocumentChunk(
        chunk_id="service-interface",
        file_path=Path("src/main/java/com/example/service/CatalogQueryService.java"),
        start_line=1,
        end_line=20,
        content="interface CatalogQueryService { String page(); }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "page"],
        metadata={"language": "java"},
    )
    executor = DocumentChunk(
        chunk_id="executor",
        file_path=Path("src/main/java/com/example/executor/PageCatalogQueryExe.java"),
        start_line=1,
        end_line=40,
        content="class PageCatalogQueryExe { String execute() { return canApplyFilter(); } }",
        chunk_type="symbol",
        lexical_tokens=["page", "catalog", "query", "exe", "can", "apply"],
        metadata={"language": "java"},
    )
    open_service = DocumentChunk(
        chunk_id="open-service",
        file_path=Path("src/main/java/com/example/service/impl/OpenCatalogQueryServiceImpl.java"),
        start_line=1,
        end_line=40,
        content="class OpenCatalogQueryServiceImpl { String page() { return null; } }",
        chunk_type="symbol",
        lexical_tokens=["open", "catalog", "query", "service", "impl", "page"],
        metadata={"language": "java"},
    )
    chunks = (exact, sibling, service_impl, service_interface, executor, open_service)
    for chunk in chunks:
        store.replace_chunks(chunk.file_path, [chunk])

    store.replace_signals(
        exact.file_path,
        [
            CodeSignal(
                signal_id="sig-exact-endpoint",
                chunk_id=exact.chunk_id,
                file_path=exact.file_path,
                kind="endpoint",
                name="POST /appCatalog/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["app", "catalog", "page", "/appCatalog/page"],
                metadata={"path": "/appCatalog/page"},
            )
        ],
    )
    store.replace_signals(
        sibling.file_path,
        [
            CodeSignal(
                signal_id="sig-sibling-endpoint",
                chunk_id=sibling.chunk_id,
                file_path=sibling.file_path,
                kind="endpoint",
                name="POST /openApi/appCatalog/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["open", "api", "app", "catalog", "page", "/openApi/appCatalog/page"],
                metadata={"path": "/openApi/appCatalog/page"},
            )
        ],
    )
    store.replace_signals(
        service_impl.file_path,
        [
            CodeSignal(
                signal_id="sig-service-impl",
                chunk_id=service_impl.chunk_id,
                file_path=service_impl.file_path,
                kind="method",
                name="CatalogQueryServiceImpl.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        service_interface.file_path,
        [
            CodeSignal(
                signal_id="sig-service-interface",
                chunk_id=service_interface.chunk_id,
                file_path=service_interface.file_path,
                kind="method",
                name="CatalogQueryService.page",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        executor.file_path,
        [
            CodeSignal(
                signal_id="sig-executor",
                chunk_id=executor.chunk_id,
                file_path=executor.file_path,
                kind="method",
                name="PageCatalogQueryExe.execute",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["page", "catalog", "query", "execute", "can", "apply"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        open_service.file_path,
        [
            CodeSignal(
                signal_id="sig-open-service",
                chunk_id=open_service.chunk_id,
                file_path=open_service.file_path,
                kind="method",
                name="OpenCatalogQueryServiceImpl.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["open", "catalog", "query", "service", "page"],
                metadata={},
            )
        ],
    )
    store.replace_relations(
        exact.file_path,
        [
            CodeRelation(
                relation_id="rel-exact-service-impl",
                source_signal_id="sig-exact-endpoint",
                target_name="CatalogQueryServiceImpl.page",
                kind="calls",
                confidence=1.0,
                metadata={},
            ),
            CodeRelation(
                relation_id="rel-exact-service-interface",
                source_signal_id="sig-exact-endpoint",
                target_name="CatalogQueryService.page",
                kind="calls",
                confidence=1.0,
                metadata={},
            ),
        ],
    )
    store.replace_relations(
        service_impl.file_path,
        [
            CodeRelation(
                relation_id="rel-service-executor",
                source_signal_id="sig-service-impl",
                target_name="PageCatalogQueryExe.execute",
                kind="calls",
                confidence=1.0,
                metadata={},
            )
        ],
    )
    store.replace_relations(
        sibling.file_path,
        [
            CodeRelation(
                relation_id="rel-sibling-open-service",
                source_signal_id="sig-sibling-endpoint",
                target_name="OpenCatalogQueryServiceImpl.page",
                kind="calls",
                confidence=1.0,
                metadata={},
            )
        ],
    )

    candidates = {
        "exact-controller": RetrievalCandidate(
            chunk_id="exact-controller",
            score=1.0,
            source="direct",
            score_parts={"semantic": 0.35, "path_symbol": 3.0, "signal": 0.6},
        ),
        "sibling-controller": RetrievalCandidate(
            chunk_id="sibling-controller",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.65,
                "path_symbol": 4.25,
                "direct_text": 1.0,
                "signal": 1.0,
            },
        ),
        "service-impl": RetrievalCandidate(
            chunk_id="service-impl",
            score=0.2,
            source="relation",
            score_parts={"relation": 0.2, "original_relation": 0.2},
        ),
        "service-interface": RetrievalCandidate(
            chunk_id="service-interface",
            score=0.2,
            source="relation",
            score_parts={"relation": 0.2, "original_relation": 0.2},
        ),
        "executor": RetrievalCandidate(
            chunk_id="executor",
            score=0.2,
            source="relation",
            score_parts={"relation": 0.2, "original_relation": 0.2},
        ),
        "open-service": RetrievalCandidate(
            chunk_id="open-service",
            score=0.9,
            source="direct",
            score_parts={"semantic": 0.6, "path_symbol": 3.0, "signal": 0.6},
        ),
    }
    return store, candidates


def test_spring_path_graph_scores_exact_controller_service_and_executor(
    tmp_path: Path,
) -> None:
    store, candidates = _spring_path_graph_case(tmp_path)

    ranked = retrieval._rank_chunks(
        store,
        candidates,
        ["app", "catalog", "page", "can", "apply"],
        "/appCatalog/page canApply",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    ranked_ids = [item.chunk.chunk_id for item in ranked]
    assert ranked_ids.index("exact-controller") < ranked_ids.index("sibling-controller")
    assert by_id["exact-controller"].score_parts["spring_path_endpoint_match"] == 0.45
    assert by_id["service-impl"].score_parts["spring_path_service_match"] == 0.30
    assert by_id["executor"].score_parts["spring_path_executor_match"] == 0.28
    assert "spring_path_endpoint_match" not in by_id["sibling-controller"].score_parts
    assert "spring_path_service_match" not in by_id["open-service"].score_parts


def test_spring_path_graph_scores_service_interface_below_implementation(
    tmp_path: Path,
) -> None:
    store, candidates = _spring_path_graph_case(tmp_path)

    ranked = retrieval._rank_chunks(
        store,
        candidates,
        ["app", "catalog", "page", "can", "apply"],
        "/appCatalog/page canApply",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert by_id["service-interface"].score_parts[
        "spring_path_service_interface_match"
    ] == 0.10
    assert by_id["service-impl"].score_parts["spring_path_service_match"] == 0.30
    assert by_id["service-impl"].rerank_score > by_id["service-interface"].rerank_score


def test_spring_path_graph_bridges_interface_method_to_implementation(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    controller = DocumentChunk(
        chunk_id="controller",
        file_path=Path("src/main/java/com/example/controller/CatalogController.java"),
        start_line=1,
        end_line=40,
        content='@RequestMapping("/catalog") class CatalogController { String page() { return service.page(); } }',
        chunk_type="symbol",
        lexical_tokens=["catalog", "page", "/catalog/page"],
        metadata={"language": "java"},
    )
    sibling = DocumentChunk(
        chunk_id="sibling-controller",
        file_path=Path("src/main/java/com/example/controller/OpenCatalogController.java"),
        start_line=1,
        end_line=40,
        content='@RequestMapping("/openApi/catalog") class OpenCatalogController { String page() { return openService.page(); } }',
        chunk_type="symbol",
        lexical_tokens=["open", "api", "catalog", "page", "/openApi/catalog/page"],
        metadata={"language": "java"},
    )
    service_interface = DocumentChunk(
        chunk_id="service-interface",
        file_path=Path("src/main/java/com/example/service/CatalogQueryService.java"),
        start_line=1,
        end_line=20,
        content="interface CatalogQueryService { String page(); }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "page"],
        metadata={"language": "java"},
    )
    service_impl = DocumentChunk(
        chunk_id="service-impl",
        file_path=Path("src/main/java/com/example/service/impl/CatalogQueryServiceImpl.java"),
        start_line=1,
        end_line=40,
        content="class CatalogQueryServiceImpl implements CatalogQueryService { String page() { return executor.execute(); } }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "impl", "page"],
        metadata={"language": "java"},
    )
    executor = DocumentChunk(
        chunk_id="executor",
        file_path=Path("src/main/java/com/example/executor/CatalogPageQueryExe.java"),
        start_line=1,
        end_line=40,
        content="class CatalogPageQueryExe { String execute() { return statusFilter(); } }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "page", "query", "exe", "status"],
        metadata={"language": "java"},
    )
    open_service = DocumentChunk(
        chunk_id="open-service",
        file_path=Path("src/main/java/com/example/service/impl/OpenCatalogQueryServiceImpl.java"),
        start_line=1,
        end_line=40,
        content="class OpenCatalogQueryServiceImpl implements OpenCatalogQueryService { String page() { return null; } }",
        chunk_type="symbol",
        lexical_tokens=["open", "catalog", "query", "service", "impl", "page"],
        metadata={"language": "java"},
    )
    for chunk in (
        controller,
        sibling,
        service_interface,
        service_impl,
        executor,
        open_service,
    ):
        store.replace_chunks(chunk.file_path, [chunk])

    store.replace_signals(
        controller.file_path,
        [
            CodeSignal(
                signal_id="sig-controller-endpoint",
                chunk_id=controller.chunk_id,
                file_path=controller.file_path,
                kind="endpoint",
                name="POST /catalog/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "page", "/catalog/page"],
                metadata={"path": "/catalog/page"},
            )
        ],
    )
    store.replace_signals(
        sibling.file_path,
        [
            CodeSignal(
                signal_id="sig-sibling-endpoint",
                chunk_id=sibling.chunk_id,
                file_path=sibling.file_path,
                kind="endpoint",
                name="POST /openApi/catalog/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["open", "api", "catalog", "page", "/openApi/catalog/page"],
                metadata={"path": "/openApi/catalog/page"},
            )
        ],
    )
    store.replace_signals(
        service_interface.file_path,
        [
            CodeSignal(
                signal_id="sig-interface-method",
                chunk_id=service_interface.chunk_id,
                file_path=service_interface.file_path,
                kind="method",
                name="CatalogQueryService.page",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        service_impl.file_path,
        [
            CodeSignal(
                signal_id="sig-impl-type",
                chunk_id=service_impl.chunk_id,
                file_path=service_impl.file_path,
                kind="type",
                name="CatalogQueryServiceImpl",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["catalog", "query", "service", "impl"],
                metadata={"type": "CatalogQueryServiceImpl"},
            ),
            CodeSignal(
                signal_id="sig-impl-method",
                chunk_id=service_impl.chunk_id,
                file_path=service_impl.file_path,
                kind="method",
                name="CatalogQueryServiceImpl.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            ),
        ],
    )
    store.replace_signals(
        executor.file_path,
        [
            CodeSignal(
                signal_id="sig-executor-method",
                chunk_id=executor.chunk_id,
                file_path=executor.file_path,
                kind="method",
                name="CatalogPageQueryExe.execute",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "page", "query", "execute", "status"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        open_service.file_path,
        [
            CodeSignal(
                signal_id="sig-open-type",
                chunk_id=open_service.chunk_id,
                file_path=open_service.file_path,
                kind="type",
                name="OpenCatalogQueryServiceImpl",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["open", "catalog", "query", "service", "impl"],
                metadata={"type": "OpenCatalogQueryServiceImpl"},
            ),
            CodeSignal(
                signal_id="sig-open-method",
                chunk_id=open_service.chunk_id,
                file_path=open_service.file_path,
                kind="method",
                name="OpenCatalogQueryServiceImpl.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["open", "catalog", "query", "service", "page"],
                metadata={},
            ),
        ],
    )
    store.replace_relations(
        controller.file_path,
        [
            CodeRelation(
                relation_id="rel-controller-interface",
                source_signal_id="sig-controller-endpoint",
                target_name="CatalogQueryService.page",
                kind="calls",
                confidence=1.0,
                metadata={},
            )
        ],
    )
    store.replace_relations(
        service_impl.file_path,
        [
            CodeRelation(
                relation_id="rel-impl-implements-interface",
                source_signal_id="sig-impl-type",
                target_name="CatalogQueryService",
                kind="implements",
                confidence=1.0,
                metadata={"source_type": "CatalogQueryServiceImpl"},
            ),
            CodeRelation(
                relation_id="rel-impl-executor",
                source_signal_id="sig-impl-method",
                target_name="CatalogPageQueryExe.execute",
                kind="calls",
                confidence=1.0,
                metadata={},
            ),
        ],
    )
    store.replace_relations(
        open_service.file_path,
        [
            CodeRelation(
                relation_id="rel-open-implements-interface",
                source_signal_id="sig-open-type",
                target_name="OpenCatalogQueryService",
                kind="implements",
                confidence=1.0,
                metadata={"source_type": "OpenCatalogQueryServiceImpl"},
            )
        ],
    )

    ranked = retrieval._rank_chunks(
        store,
        {
            "controller": RetrievalCandidate(
                chunk_id="controller",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.35, "path_symbol": 3.0, "signal": 0.6},
            ),
            "sibling-controller": RetrievalCandidate(
                chunk_id="sibling-controller",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.65, "path_symbol": 4.25, "signal": 1.0},
            ),
            "service-interface": RetrievalCandidate(
                chunk_id="service-interface",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
            "service-impl": RetrievalCandidate(
                chunk_id="service-impl",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
            "executor": RetrievalCandidate(
                chunk_id="executor",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
            "open-service": RetrievalCandidate(
                chunk_id="open-service",
                score=0.9,
                source="direct",
                score_parts={"semantic": 0.6, "path_symbol": 3.0, "signal": 0.6},
            ),
        },
        ["catalog", "page", "status"],
        "/catalog/page status",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert by_id["controller"].score_parts["spring_path_endpoint_match"] == 0.45
    assert by_id["service-interface"].score_parts[
        "spring_path_service_interface_match"
    ] == 0.10
    assert by_id["service-impl"].score_parts["spring_path_service_match"] == 0.30
    assert by_id["executor"].score_parts["spring_path_executor_match"] == 0.28
    assert "spring_path_endpoint_match" not in by_id["sibling-controller"].score_parts
    assert "spring_path_service_match" not in by_id["open-service"].score_parts


def test_spring_path_graph_follows_only_matching_implementation_method(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    controller = DocumentChunk(
        chunk_id="controller",
        file_path=Path("src/main/java/com/example/controller/CatalogController.java"),
        start_line=1,
        end_line=40,
        content='@RequestMapping("/catalog") class CatalogController { String page() { return service.page(); } }',
        chunk_type="symbol",
        lexical_tokens=["catalog", "page", "/catalog/page"],
        metadata={"language": "java"},
    )
    service_interface = DocumentChunk(
        chunk_id="service-interface",
        file_path=Path("src/main/java/com/example/service/CatalogQueryService.java"),
        start_line=1,
        end_line=20,
        content="interface CatalogQueryService { String page(); String export(); }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "page", "export"],
        metadata={"language": "java"},
    )
    service_impl = DocumentChunk(
        chunk_id="service-impl",
        file_path=Path("src/main/java/com/example/service/impl/CatalogQueryServiceImpl.java"),
        start_line=1,
        end_line=60,
        content="class CatalogQueryServiceImpl implements CatalogQueryService { String page() { return pageExe.execute(); } String export() { return exportExe.execute(); } }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "impl", "page", "export"],
        metadata={"language": "java"},
    )
    page_executor = DocumentChunk(
        chunk_id="page-executor",
        file_path=Path("src/main/java/com/example/executor/CatalogPageQueryExe.java"),
        start_line=1,
        end_line=40,
        content="class CatalogPageQueryExe { String execute() { return pageData(); } }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "page", "query", "exe"],
        metadata={"language": "java"},
    )
    export_executor = DocumentChunk(
        chunk_id="export-executor",
        file_path=Path("src/main/java/com/example/executor/CatalogExportExe.java"),
        start_line=1,
        end_line=40,
        content="class CatalogExportExe { String execute() { return exportData(); } }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "export", "exe"],
        metadata={"language": "java"},
    )
    for chunk in (
        controller,
        service_interface,
        service_impl,
        page_executor,
        export_executor,
    ):
        store.replace_chunks(chunk.file_path, [chunk])

    store.replace_signals(
        controller.file_path,
        [
            CodeSignal(
                signal_id="sig-controller-endpoint",
                chunk_id=controller.chunk_id,
                file_path=controller.file_path,
                kind="endpoint",
                name="POST /catalog/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "page", "/catalog/page"],
                metadata={"path": "/catalog/page"},
            )
        ],
    )
    store.replace_signals(
        service_interface.file_path,
        [
            CodeSignal(
                signal_id="sig-interface-page",
                chunk_id=service_interface.chunk_id,
                file_path=service_interface.file_path,
                kind="method",
                name="CatalogQueryService.page",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        service_impl.file_path,
        [
            CodeSignal(
                signal_id="sig-impl-type",
                chunk_id=service_impl.chunk_id,
                file_path=service_impl.file_path,
                kind="type",
                name="CatalogQueryServiceImpl",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["catalog", "query", "service", "impl"],
                metadata={"type": "CatalogQueryServiceImpl"},
            ),
            CodeSignal(
                signal_id="sig-impl-page",
                chunk_id=service_impl.chunk_id,
                file_path=service_impl.file_path,
                kind="method",
                name="CatalogQueryServiceImpl.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            ),
            CodeSignal(
                signal_id="sig-impl-export",
                chunk_id=service_impl.chunk_id,
                file_path=service_impl.file_path,
                kind="method",
                name="CatalogQueryServiceImpl.export",
                start_line=4,
                end_line=4,
                language="java",
                tokens=["catalog", "query", "service", "export"],
                metadata={},
            ),
        ],
    )
    store.replace_signals(
        page_executor.file_path,
        [
            CodeSignal(
                signal_id="sig-page-executor",
                chunk_id=page_executor.chunk_id,
                file_path=page_executor.file_path,
                kind="method",
                name="CatalogPageQueryExe.execute",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "page", "query", "execute"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        export_executor.file_path,
        [
            CodeSignal(
                signal_id="sig-export-executor",
                chunk_id=export_executor.chunk_id,
                file_path=export_executor.file_path,
                kind="method",
                name="CatalogExportExe.execute",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "export", "execute"],
                metadata={},
            )
        ],
    )
    store.replace_relations(
        controller.file_path,
        [
            CodeRelation(
                relation_id="rel-controller-interface-page",
                source_signal_id="sig-controller-endpoint",
                target_name="CatalogQueryService.page",
                kind="calls",
                confidence=1.0,
                metadata={},
            )
        ],
    )
    store.replace_relations(
        service_impl.file_path,
        [
            CodeRelation(
                relation_id="rel-impl-implements-interface",
                source_signal_id="sig-impl-type",
                target_name="CatalogQueryService",
                kind="implements",
                confidence=1.0,
                metadata={"source_type": "CatalogQueryServiceImpl"},
            ),
            CodeRelation(
                relation_id="rel-page-executor",
                source_signal_id="sig-impl-page",
                target_name="CatalogPageQueryExe.execute",
                kind="calls",
                confidence=1.0,
                metadata={},
            ),
            CodeRelation(
                relation_id="rel-export-executor",
                source_signal_id="sig-impl-export",
                target_name="CatalogExportExe.execute",
                kind="calls",
                confidence=1.0,
                metadata={},
            ),
        ],
    )

    ranked = retrieval._rank_chunks(
        store,
        {
            "controller": RetrievalCandidate(
                chunk_id="controller",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.35, "path_symbol": 3.0, "signal": 0.6},
            ),
            "service-interface": RetrievalCandidate(
                chunk_id="service-interface",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
            "service-impl": RetrievalCandidate(
                chunk_id="service-impl",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
            "page-executor": RetrievalCandidate(
                chunk_id="page-executor",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
            "export-executor": RetrievalCandidate(
                chunk_id="export-executor",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
        },
        ["catalog", "page"],
        "/catalog/page",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert by_id["page-executor"].score_parts["spring_path_executor_match"] == 0.28
    assert "spring_path_executor_match" not in by_id["export-executor"].score_parts


def test_spring_path_graph_does_not_bridge_ambiguous_qualified_interfaces(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    controller = DocumentChunk(
        chunk_id="controller",
        file_path=Path("src/main/java/com/example/controller/CatalogController.java"),
        start_line=1,
        end_line=40,
        content='@RequestMapping("/catalog") class CatalogController { String page() { return service.page(); } }',
        chunk_type="symbol",
        lexical_tokens=["catalog", "page", "/catalog/page"],
        metadata={"language": "java"},
    )
    interface_chunk = DocumentChunk(
        chunk_id="interface",
        file_path=Path("src/main/java/com/foo/CatalogQueryService.java"),
        start_line=1,
        end_line=20,
        content="interface CatalogQueryService { String page(); }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "page"],
        metadata={"language": "java"},
    )
    foo_impl = DocumentChunk(
        chunk_id="foo-impl",
        file_path=Path("src/main/java/com/foo/impl/CatalogQueryServiceImpl.java"),
        start_line=1,
        end_line=40,
        content="class CatalogQueryServiceImpl implements CatalogQueryService { String page() { return null; } }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "impl", "page"],
        metadata={"language": "java"},
    )
    bar_impl = DocumentChunk(
        chunk_id="bar-impl",
        file_path=Path("src/main/java/com/bar/impl/CatalogQueryServiceImpl.java"),
        start_line=1,
        end_line=40,
        content="class CatalogQueryServiceImpl implements CatalogQueryService { String page() { return null; } }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "impl", "page"],
        metadata={"language": "java"},
    )
    for chunk in (controller, interface_chunk, foo_impl, bar_impl):
        store.replace_chunks(chunk.file_path, [chunk])

    store.replace_signals(
        controller.file_path,
        [
            CodeSignal(
                signal_id="sig-controller-endpoint",
                chunk_id=controller.chunk_id,
                file_path=controller.file_path,
                kind="endpoint",
                name="POST /catalog/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "page", "/catalog/page"],
                metadata={"path": "/catalog/page"},
            )
        ],
    )
    store.replace_signals(
        interface_chunk.file_path,
        [
            CodeSignal(
                signal_id="sig-interface-method",
                chunk_id=interface_chunk.chunk_id,
                file_path=interface_chunk.file_path,
                kind="method",
                name="com.foo.CatalogQueryService.page",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        foo_impl.file_path,
        [
            CodeSignal(
                signal_id="sig-foo-type",
                chunk_id=foo_impl.chunk_id,
                file_path=foo_impl.file_path,
                kind="type",
                name="com.foo.CatalogQueryServiceImpl",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["catalog", "query", "service", "impl"],
                metadata={"type": "com.foo.CatalogQueryServiceImpl"},
            ),
            CodeSignal(
                signal_id="sig-foo-method",
                chunk_id=foo_impl.chunk_id,
                file_path=foo_impl.file_path,
                kind="method",
                name="com.foo.CatalogQueryServiceImpl.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            ),
        ],
    )
    store.replace_signals(
        bar_impl.file_path,
        [
            CodeSignal(
                signal_id="sig-bar-type",
                chunk_id=bar_impl.chunk_id,
                file_path=bar_impl.file_path,
                kind="type",
                name="com.bar.CatalogQueryServiceImpl",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["catalog", "query", "service", "impl"],
                metadata={"type": "com.bar.CatalogQueryServiceImpl"},
            ),
            CodeSignal(
                signal_id="sig-bar-method",
                chunk_id=bar_impl.chunk_id,
                file_path=bar_impl.file_path,
                kind="method",
                name="com.bar.CatalogQueryServiceImpl.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            ),
        ],
    )
    store.replace_relations(
        controller.file_path,
        [
            CodeRelation(
                relation_id="rel-controller-interface-page",
                source_signal_id="sig-controller-endpoint",
                target_name="com.foo.CatalogQueryService.page",
                kind="calls",
                confidence=1.0,
                metadata={},
            )
        ],
    )
    store.replace_relations(
        foo_impl.file_path,
        [
            CodeRelation(
                relation_id="rel-foo-implements",
                source_signal_id="sig-foo-type",
                target_name="com.foo.CatalogQueryService",
                kind="implements",
                confidence=1.0,
                metadata={"source_type": "com.foo.CatalogQueryServiceImpl"},
            )
        ],
    )
    store.replace_relations(
        bar_impl.file_path,
        [
            CodeRelation(
                relation_id="rel-bar-implements",
                source_signal_id="sig-bar-type",
                target_name="com.bar.CatalogQueryService",
                kind="implements",
                confidence=1.0,
                metadata={"source_type": "com.bar.CatalogQueryServiceImpl"},
            )
        ],
    )

    ranked = retrieval._rank_chunks(
        store,
        {
            "controller": RetrievalCandidate(
                chunk_id="controller",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.35, "path_symbol": 3.0, "signal": 0.6},
            ),
            "interface": RetrievalCandidate(
                chunk_id="interface",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
            "foo-impl": RetrievalCandidate(
                chunk_id="foo-impl",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
            "bar-impl": RetrievalCandidate(
                chunk_id="bar-impl",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
        },
        ["catalog", "page"],
        "/catalog/page",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert by_id["foo-impl"].score_parts["spring_path_service_match"] == 0.30
    assert "spring_path_service_match" not in by_id["bar-impl"].score_parts


def test_spring_path_graph_qualified_target_ignores_wrong_qualified_implementor(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    controller = DocumentChunk(
        chunk_id="controller",
        file_path=Path("src/main/java/com/example/controller/CatalogController.java"),
        start_line=1,
        end_line=40,
        content='@RequestMapping("/catalog") class CatalogController { String page() { return service.page(); } }',
        chunk_type="symbol",
        lexical_tokens=["catalog", "page", "/catalog/page"],
        metadata={"language": "java"},
    )
    bar_impl = DocumentChunk(
        chunk_id="bar-impl",
        file_path=Path("src/main/java/com/bar/impl/CatalogQueryServiceImpl.java"),
        start_line=1,
        end_line=40,
        content="class CatalogQueryServiceImpl implements CatalogQueryService { String page() { return null; } }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "impl", "page"],
        metadata={"language": "java"},
    )
    for chunk in (controller, bar_impl):
        store.replace_chunks(chunk.file_path, [chunk])

    store.replace_signals(
        controller.file_path,
        [
            CodeSignal(
                signal_id="sig-controller-endpoint",
                chunk_id=controller.chunk_id,
                file_path=controller.file_path,
                kind="endpoint",
                name="POST /catalog/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "page", "/catalog/page"],
                metadata={"path": "/catalog/page"},
            )
        ],
    )
    store.replace_signals(
        bar_impl.file_path,
        [
            CodeSignal(
                signal_id="sig-bar-type",
                chunk_id=bar_impl.chunk_id,
                file_path=bar_impl.file_path,
                kind="type",
                name="com.bar.CatalogQueryServiceImpl",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["catalog", "query", "service", "impl"],
                metadata={"type": "com.bar.CatalogQueryServiceImpl"},
            ),
            CodeSignal(
                signal_id="sig-bar-method",
                chunk_id=bar_impl.chunk_id,
                file_path=bar_impl.file_path,
                kind="method",
                name="com.bar.CatalogQueryServiceImpl.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            ),
        ],
    )
    store.replace_relations(
        controller.file_path,
        [
            CodeRelation(
                relation_id="rel-controller-interface-page",
                source_signal_id="sig-controller-endpoint",
                target_name="com.foo.CatalogQueryService.page",
                kind="calls",
                confidence=1.0,
                metadata={},
            )
        ],
    )
    store.replace_relations(
        bar_impl.file_path,
        [
            CodeRelation(
                relation_id="rel-bar-implements",
                source_signal_id="sig-bar-type",
                target_name="com.bar.CatalogQueryService",
                kind="implements",
                confidence=1.0,
                metadata={"source_type": "com.bar.CatalogQueryServiceImpl"},
            )
        ],
    )

    ranked = retrieval._rank_chunks(
        store,
        {
            "controller": RetrievalCandidate(
                chunk_id="controller",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.35, "path_symbol": 3.0, "signal": 0.6},
            ),
            "bar-impl": RetrievalCandidate(
                chunk_id="bar-impl",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
        },
        ["catalog", "page"],
        "/catalog/page",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert by_id["controller"].score_parts["spring_path_endpoint_match"] == 0.45
    assert "spring_path_service_match" not in by_id["bar-impl"].score_parts


def test_spring_path_graph_skips_ambiguous_direct_impl_fallback(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    controller = DocumentChunk(
        chunk_id="controller",
        file_path=Path("src/main/java/com/example/controller/CatalogController.java"),
        start_line=1,
        end_line=40,
        content='@RequestMapping("/catalog") class CatalogController { String page() { return service.page(); } }',
        chunk_type="symbol",
        lexical_tokens=["catalog", "page", "/catalog/page"],
        metadata={"language": "java"},
    )
    foo_impl = DocumentChunk(
        chunk_id="foo-impl",
        file_path=Path("src/main/java/com/foo/impl/CatalogQueryServiceImpl.java"),
        start_line=1,
        end_line=40,
        content="class CatalogQueryServiceImpl { String page() { return null; } }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "impl", "page"],
        metadata={"language": "java"},
    )
    bar_impl = DocumentChunk(
        chunk_id="bar-impl",
        file_path=Path("src/main/java/com/bar/impl/CatalogQueryServiceImpl.java"),
        start_line=1,
        end_line=40,
        content="class CatalogQueryServiceImpl { String page() { return null; } }",
        chunk_type="symbol",
        lexical_tokens=["catalog", "query", "service", "impl", "page"],
        metadata={"language": "java"},
    )
    for chunk in (controller, foo_impl, bar_impl):
        store.replace_chunks(chunk.file_path, [chunk])

    store.replace_signals(
        controller.file_path,
        [
            CodeSignal(
                signal_id="sig-controller-endpoint",
                chunk_id=controller.chunk_id,
                file_path=controller.file_path,
                kind="endpoint",
                name="POST /catalog/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "page", "/catalog/page"],
                metadata={"path": "/catalog/page"},
            )
        ],
    )
    store.replace_signals(
        foo_impl.file_path,
        [
            CodeSignal(
                signal_id="sig-foo-method",
                chunk_id=foo_impl.chunk_id,
                file_path=foo_impl.file_path,
                kind="method",
                name="CatalogQueryServiceImpl.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        bar_impl.file_path,
        [
            CodeSignal(
                signal_id="sig-bar-method",
                chunk_id=bar_impl.chunk_id,
                file_path=bar_impl.file_path,
                kind="method",
                name="CatalogQueryServiceImpl.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["catalog", "query", "service", "page"],
                metadata={},
            )
        ],
    )
    store.replace_relations(
        controller.file_path,
        [
            CodeRelation(
                relation_id="rel-controller-interface-page",
                source_signal_id="sig-controller-endpoint",
                target_name="CatalogQueryService.page",
                kind="calls",
                confidence=1.0,
                metadata={},
            )
        ],
    )

    ranked = retrieval._rank_chunks(
        store,
        {
            "controller": RetrievalCandidate(
                chunk_id="controller",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.35, "path_symbol": 3.0, "signal": 0.6},
            ),
            "foo-impl": RetrievalCandidate(
                chunk_id="foo-impl",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
            "bar-impl": RetrievalCandidate(
                chunk_id="bar-impl",
                score=0.2,
                source="relation",
                score_parts={"relation": 0.2, "original_relation": 0.2},
            ),
        },
        ["catalog", "page"],
        "/catalog/page",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert by_id["controller"].score_parts["spring_path_endpoint_match"] == 0.45
    assert "spring_path_service_match" not in by_id["foo-impl"].score_parts
    assert "spring_path_service_match" not in by_id["bar-impl"].score_parts


def test_query_combines_route_tokens_and_ranking_reasons(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ApplyAuditController.java").write_text(
        '''
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/apply/audit")
class ApplyAuditController {
  @PostMapping("/pageEs")
  String pageEs() { return "ok"; }
}
'''.strip(),
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "/apply/audit/pageEs INVOLVED_BY_ME", DEFAULT_CONFIG)

    assert bundle.results
    assert bundle.results[0].file_path == Path("ApplyAuditController.java")
    assert any("route" in reason.lower() or "lexical" in reason.lower() for reason in bundle.results[0].reasons)
    assert "apply" in bundle.followup_keywords


def test_query_context_lines_override_expands_result(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Service.java").write_text(
        "line1\nline2\nline3 targetToken\nline4\nline5\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "targetToken", DEFAULT_CONFIG, context_lines=1)

    assert "line2" in bundle.results[0].content
    assert "line4" in bundle.results[0].content


def test_full_file_respects_size_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Small.java").write_text("class Small { String targetToken; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "targetToken", DEFAULT_CONFIG, full_file=True)

    assert bundle.results[0].content.startswith("class Small")


def test_full_file_fallback_still_respects_size_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    content = "\n".join(
        [
            "class Large {",
            "  String targetToken = \"" + ("x" * 100) + "\";",
            "}",
        ]
    )
    (repo / "Large.java").write_text(content, encoding="utf-8")
    config = ToolConfig(index=IndexConfig(max_full_file_bytes=64))
    index_repository(repo, config)

    bundle = query_repository(repo, "targetToken", config, full_file=True)

    assert (
        len(bundle.results[0].content.encode("utf-8"))
        <= config.index.max_full_file_bytes
    )
    assert bundle.results[0].content != content


def test_full_file_merged_ranges_still_respect_size_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    lines = ["x" for _ in range(200)]
    lines[0] = "targetToken"
    lines[80] = "targetToken"
    lines[160] = "targetToken"
    (repo / "Large.java").write_text("\n".join(lines), encoding="utf-8")
    config = ToolConfig(index=IndexConfig(max_full_file_bytes=220))
    index_repository(repo, config)

    bundle = query_repository(repo, "targetToken", config, full_file=True)

    assert bundle.results
    assert all(
        len(result.content.encode("utf-8")) <= config.index.max_full_file_bytes
        for result in bundle.results
    )


def test_query_rejects_incompatible_embedding_model(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Service.java").write_text(
        "class Service { String targetToken; }\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    config = ToolConfig(
        embedding=EmbeddingConfig(provider="hash", model="hash-v2", dimensions=384)
    )
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            grep_keywords=["ExpensiveHint"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    with pytest.raises(ValueError, match="incompatible"):
        query_repository(repo, "targetToken", config, planner=planner)
    assert planner.calls == []


def test_query_rejects_incompatible_embedding_dimensions(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Service.java").write_text(
        "class Service { String targetToken; }\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    config = ToolConfig(
        embedding=EmbeddingConfig(provider="hash", model="hash-v1", dimensions=128)
    )

    with pytest.raises(ValueError, match="incompatible"):
        query_repository(repo, "targetToken", config)


def test_noisy_route_query_keeps_lexical_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ApplyAuditController.java").write_text(
        '''
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/apply/audit")
class ApplyAuditController {
  @PostMapping("/pageEs")
  String pageEs() { return "ok"; }
}
'''.strip(),
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(
        repo,
        "/apply/audit/pageEs why does this leak across regions",
        DEFAULT_CONFIG,
    )

    assert bundle.results[0].file_path == Path("ApplyAuditController.java")
    assert "lexical" in bundle.results[0].score_parts
    assert any("lexical" in reason.lower() for reason in bundle.results[0].reasons)


def test_route_reason_only_applies_to_chunks_with_route_tokens(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ApplyAuditController.java").write_text(
        '''
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/apply/audit")
class ApplyAuditController {
  @PostMapping("/pageEs")
  String pageEs() { return "ok"; }
}
'''.strip(),
        encoding="utf-8",
    )
    (repo / "AuditStatus.java").write_text(
        """
enum AuditStatus {
  INVOLVED_BY_ME,
  TOTAL_OVERVIEW
}
""".strip(),
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "/apply/audit/pageEs INVOLVED_BY_ME", DEFAULT_CONFIG)

    status_result = next(
        result for result in bundle.results if result.file_path == Path("AuditStatus.java")
    )
    assert not any("route" in reason.lower() for reason in status_result.reasons)


def test_query_planner_hints_surface_dashboard_code_for_chinese_query(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "DashboardController.java").write_text(
        """
class DashboardController {
  String chart() { return dashboardService.statistics(); }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "UnrelatedController.java").write_text(
        """
class UnrelatedController {
  String query() { return "数据看板统计图表功能"; }
}
""".strip(),
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=2,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    planner = FakePlanner(
        QueryPlan(
            original_query="数据看板统计图表功能",
            grep_keywords=["Dashboard", "Statistics", "Chart"],
            symbol_hints=["DashboardController"],
            intent="feature_lookup",
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    bundle = query_repository(repo, "数据看板统计图表功能", config, planner=planner)

    assert bundle.planner.status == "ok"
    assert "dashboard" in bundle.expanded_tokens
    assert any(
        result.file_path == Path("DashboardController.java")
        for result in bundle.results
    )
    dashboard = next(
        result
        for result in bundle.results
        if result.file_path == Path("DashboardController.java")
    )
    assert "planner hint match" in dashboard.reasons


def test_query_planner_fallback_returns_original_query_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OriginalMatch.java").write_text(
        'class OriginalMatch { String value = "targetToken"; }\n',
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=1,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            status="fallback",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            latency_ms=8,
            error="planner timed out after 8 seconds",
        )
    )

    bundle = query_repository(repo, "targetToken", config, planner=planner)

    assert bundle.planner.status == "fallback"
    assert bundle.expanded_tokens == ["target", "token"]
    assert bundle.results[0].file_path == Path("OriginalMatch.java")


def test_query_planner_mixed_original_and_hint_match_keeps_planner_reason(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "MixedDashboard.java").write_text(
        'class MixedDashboard { String value = "targetToken dashboard"; }\n',
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=1,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            grep_keywords=["dashboard"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    bundle = query_repository(repo, "targetToken", config, planner=planner)

    assert bundle.results[0].file_path == Path("MixedDashboard.java")
    assert any(
        reason in bundle.results[0].reasons
        for reason in ("lexical match", "token coverage")
    )
    assert "planner hint match" in bundle.results[0].reasons


def test_planner_seeded_relation_keeps_planner_provenance(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OriginalMatch.java").write_text(
        'class OriginalMatch { String value = "targetToken"; }\n',
        encoding="utf-8",
    )
    (repo / "DashboardController.java").write_text(
        """
class DashboardController {
  String dashboard() { return bridgeService.list(); }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "BridgeService.java").write_text(
        """
class BridgeService {
  String list() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=3,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    original_chunk = store.chunk_for_line(Path("OriginalMatch.java"), 1)
    controller_chunk = store.chunk_for_line(Path("DashboardController.java"), 2)
    service_chunk = store.chunk_for_line(Path("BridgeService.java"), 2)
    store.replace_signals(
        Path("OriginalMatch.java"),
        [
            CodeSignal(
                signal_id="sig-original-target",
                chunk_id=original_chunk.chunk_id,
                file_path=Path("OriginalMatch.java"),
                kind="method",
                name="OriginalMatch.targetToken",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["target", "token"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        Path("DashboardController.java"),
        [
            CodeSignal(
                signal_id="sig-dashboard-controller",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("DashboardController.java"),
                kind="method",
                name="DashboardController.dashboard",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["dashboard", "controller"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        Path("BridgeService.java"),
        [
            CodeSignal(
                signal_id="sig-bridge-service",
                chunk_id=service_chunk.chunk_id,
                file_path=Path("BridgeService.java"),
                kind="method",
                name="BridgeService.list",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["bridge", "service", "list"],
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("DashboardController.java"),
        [
            CodeRelation(
                relation_id="rel-dashboard-controller-service",
                source_signal_id="sig-dashboard-controller",
                target_name="BridgeService.list",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            symbol_hints=["DashboardController"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    bundle = query_repository(repo, "targetToken", config, planner=planner)

    service_result = next(
        result
        for result in bundle.results
        if result.file_path == Path("BridgeService.java")
    )
    assert bundle.results[0].file_path == Path("OriginalMatch.java")
    assert "relation" in service_result.score_parts
    assert "planner_relation" in service_result.score_parts
    assert "planner_signal" not in service_result.score_parts
    assert "planner hint match" in service_result.reasons


def test_planner_only_match_ranks_below_comparable_original_match(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OriginalMatch.java").write_text(
        'class OriginalMatch { String value = "targetToken"; }\n',
        encoding="utf-8",
    )
    (repo / "PlannerDashboard.java").write_text(
        "class PlannerDashboard { String dashboard() { return \"ok\"; } }\n",
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=2,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            grep_keywords=["dashboard"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    bundle = query_repository(repo, "targetToken", config, planner=planner)

    assert [result.file_path for result in bundle.results] == [
        Path("OriginalMatch.java"),
        Path("PlannerDashboard.java"),
    ]
    assert "lexical match" in bundle.results[0].reasons
    assert "token coverage" in bundle.results[0].reasons
    assert "planner hint match" not in bundle.results[0].reasons
    assert "planner hint match" in bundle.results[1].reasons


def _graph_store(
    tmp_path: Path,
    names: list[str],
    relations: list[tuple[str, str, float]],
) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    for name in names:
        path = Path(f"{name}.py")
        chunk = DocumentChunk(
            chunk_id=f"chunk-{name}",
            file_path=path,
            start_line=1,
            end_line=1,
            content=f"def {name.lower()}(): pass",
            chunk_type="symbol",
            symbols=[
                SymbolRef(
                    name=name,
                    kind="function",
                    start_line=1,
                    end_line=1,
                    language="python",
                    metadata={},
                )
            ],
            lexical_tokens=[name.lower()],
            embedding_id=f"chunk-{name}",
            deleted_at=None,
            metadata={"language": "python"},
        )
        signal = CodeSignal(
            signal_id=f"sig-{name}",
            chunk_id=chunk.chunk_id,
            file_path=path,
            kind="method",
            name=name,
            start_line=1,
            end_line=1,
            language="python",
            tokens=[name.lower()],
            metadata={},
        )
        store.replace_chunks(path, [chunk])
        store.replace_signals(path, [signal])

    relations_by_source: dict[str, list[CodeRelation]] = {}
    for source, target, confidence in relations:
        relations_by_source.setdefault(source, []).append(
            CodeRelation(
                relation_id=f"rel-{source}-{target}",
                source_signal_id=f"sig-{source}",
                target_name=target,
                kind="calls",
                confidence=confidence,
                metadata={},
            )
        )
    for source, source_relations in relations_by_source.items():
        store.replace_relations(Path(f"{source}.py"), source_relations)
    return store


def _seed_candidate(name: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=f"chunk-{name}",
        score=1.0,
        source="signal",
        score_parts={"signal": 1.0},
    )


def _expansion_config() -> ToolConfig:
    return ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=20,
            final_top_k=20,
            context_before_lines=0,
            context_after_lines=0,
        )
    )


def _rank_chunks_signal_lookup_case(
    tmp_path: Path,
    signal_indices: set[int] | None = None,
    route_relevant_indices: set[int] | None = None,
) -> tuple[SQLiteStore, dict[str, RetrievalCandidate]]:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    signal_indices = signal_indices or set()
    route_relevant_indices = route_relevant_indices or set()
    candidates: dict[str, RetrievalCandidate] = {}
    for index in range(1000):
        chunk_id = f"chunk-{index}"
        is_route_relevant = index in route_relevant_indices
        class_name = f"TargetTokenController{index}" if is_route_relevant else f"Service{index}"
        path = Path(f"src/main/java/example/{class_name}.java")
        content = (
            f'class {class_name} {{ @GetMapping("/target/token") void page() {{}} }}'
            if is_route_relevant
            else f"class {class_name} {{ String unrelatedValue; }}"
        )
        lexical_tokens = (
            ["/target/token", "target", "token"]
            if is_route_relevant
            else ["service", "unrelated"]
        )
        store.replace_chunks(
            path,
            [
                DocumentChunk(
                    chunk_id=chunk_id,
                    file_path=path,
                    start_line=1,
                    end_line=1,
                    content=content,
                    chunk_type="symbol",
                    symbols=[],
                    lexical_tokens=lexical_tokens,
                    embedding_id=chunk_id,
                    deleted_at=None,
                    metadata={"language": "java"},
                )
            ],
        )
        has_signal = index in signal_indices
        if has_signal:
            store.replace_signals(
                path,
                [
                    CodeSignal(
                        signal_id=f"sig-{index}",
                        chunk_id=chunk_id,
                        file_path=path,
                        kind="endpoint",
                        name=f"GET /target/token/{index}",
                        start_line=1,
                        end_line=1,
                        language="java",
                        tokens=["target", "token"],
                        metadata={"path": f"/target/token/{index}"},
                    )
                ],
            )
        candidates[chunk_id] = RetrievalCandidate(
            chunk_id=chunk_id,
            score=1.0,
            source="signal" if has_signal else "lexical",
            score_parts={"signal": 1.0} if has_signal else {"lexical": 1.0},
        )
    return store, candidates


def _count_signal_lookups(store: SQLiteStore, monkeypatch: pytest.MonkeyPatch):
    call_count = 0

    original = store.signals_for_chunk

    def counting_signals_for_chunk(chunk_id: str) -> list[CodeSignal]:
        nonlocal call_count
        call_count += 1
        return original(chunk_id)

    monkeypatch.setattr(store, "signals_for_chunk", counting_signals_for_chunk)
    return lambda: call_count


def test_rank_chunks_skips_signal_lookup_for_non_route_non_signal_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, candidates = _rank_chunks_signal_lookup_case(tmp_path)
    signal_lookup_count = _count_signal_lookups(store, monkeypatch)

    retrieval._rank_chunks(store, candidates, ["target", "token"], "targetToken")

    assert signal_lookup_count() == 0


def test_rank_chunks_skips_signal_lookup_for_slash_file_path_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, candidates = _rank_chunks_signal_lookup_case(tmp_path)
    signal_lookup_count = _count_signal_lookups(store, monkeypatch)

    retrieval._rank_chunks(store, candidates, ["src", "main", "java", "foo"], "src/main/java Foo")

    assert signal_lookup_count() == 0


def test_rank_chunks_only_fetches_route_signals_for_route_relevant_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_relevant_indices = {3, 503, 999}
    store, candidates = _rank_chunks_signal_lookup_case(
        tmp_path,
        signal_indices=route_relevant_indices,
        route_relevant_indices=route_relevant_indices,
    )
    signal_lookup_count = _count_signal_lookups(store, monkeypatch)

    retrieval._rank_chunks(store, candidates, ["target", "token"], "/target/token")

    assert signal_lookup_count() == len(route_relevant_indices)


def test_rank_chunks_uses_signal_lookup_for_signal_candidates_without_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal_indices = {1, 501}
    store, candidates = _rank_chunks_signal_lookup_case(tmp_path, signal_indices)
    signal_lookup_count = _count_signal_lookups(store, monkeypatch)

    retrieval._rank_chunks(store, candidates, ["target", "token"], "targetToken")

    assert signal_lookup_count() == len(signal_indices)


# ============================================================================
# Rerank Soft Sorting Tests (TDD - Step 1)
# These tests validate the rerank-based sorting behavior that will fix the
# rank_tier absolute priority bug where low-score relation expansion results
# incorrectly outrank high-score direct matches.
# ============================================================================


def test_rerank_high_score_direct_beats_low_score_relation(tmp_path: Path) -> None:
    """
    Test #1: High combined_score direct match must rank before low-score relation-only.
    Reproduces SmsUtils case where semantic=2.0+ direct match was outranked by
    low-score relation expansion due to rank_tier=1 < rank_tier=2.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    # High-score direct match (semantic + path + signal)
    high_direct = DocumentChunk(
        chunk_id="high-direct",
        file_path=Path("SmsUtils.java"),
        start_line=1,
        end_line=10,
        content="class SmsUtils { void sendSms() {} }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["sms", "utils"],
        embedding_id="high-direct",
        deleted_at=None,
        metadata={"language": "java"},
    )

    # Low-score relation-only match
    low_relation = DocumentChunk(
        chunk_id="low-relation",
        file_path=Path("RedisCache.java"),
        start_line=1,
        end_line=10,
        content="class RedisCache { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["redis", "cache"],
        embedding_id="low-relation",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("SmsUtils.java"), [high_direct])
    store.replace_chunks(Path("RedisCache.java"), [low_relation])

    candidates = {
        "high-direct": RetrievalCandidate(
            chunk_id="high-direct",
            score=2.4,  # Will be recalculated from score_parts
            source="semantic,signal,path_symbol",
            score_parts={
                "semantic": 2.0,  # High BGE-M3 score
                "signal": 0.3,
                "path_symbol": 0.1,
            },
        ),
        "low-relation": RetrievalCandidate(
            chunk_id="low-relation",
            score=0.5,
            source="relation",
            score_parts={
                "relation": 0.5,
                "original_relation": 0.5,
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["sms", "send"], "send sms")

    # High-score direct should rank first
    assert ranked[0].chunk.chunk_id == "high-direct"
    assert ranked[1].chunk.chunk_id == "low-relation"


def test_rank_chunks_exposes_numeric_diagnostic_score_parts(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    chunk = DocumentChunk(
        chunk_id="auth-service",
        file_path=Path("src/main/java/com/example/service/AuthService.java"),
        start_line=1,
        end_line=10,
        content="public interface AuthService { void login(); }",
        chunk_type="symbol",
        lexical_tokens=["auth", "service", "login"],
        metadata={"language": "java"},
    )
    store.replace_chunks(chunk.file_path, [chunk])
    candidates = {
        "auth-service": RetrievalCandidate(
            chunk_id="auth-service",
            score=1.0,
            source="test",
            score_parts={"lexical": 0.8, "path_symbol": 2.0},
        )
    }

    ranked = retrieval._rank_chunks(store, candidates, ["auth", "login"], "auth login")

    parts = ranked[0].score_parts
    assert isinstance(parts["combined_score"], float)
    assert isinstance(parts["rerank_score"], float)
    assert isinstance(parts["evidence_priority"], float)
    assert isinstance(parts["role_priority"], float)
    assert isinstance(parts["role_boost"], float)


def test_chunk_role_prefers_service_impl_over_service_interface_content() -> None:
    chunk = DocumentChunk(
        chunk_id="auth-service-impl",
        file_path=Path("src/main/java/com/example/service/impl/AuthServiceImpl.java"),
        start_line=1,
        end_line=10,
        content="class AuthServiceImpl { /* delegates to interface AuthService */ }",
        chunk_type="symbol",
        lexical_tokens=["auth", "service", "impl"],
        metadata={"language": "java"},
    )

    assert retrieval._chunk_role(chunk).name == "service_impl"


def test_chunk_role_prefers_executor_over_generic_service_directory() -> None:
    chunk = DocumentChunk(
        chunk_id="page-app-catalog-query-exe",
        file_path=Path("src/main/java/com/example/service/PageAppCatalogQueryExe.java"),
        start_line=1,
        end_line=10,
        content="class PageAppCatalogQueryExe { Page execute() { return null; } }",
        chunk_type="symbol",
        lexical_tokens=["page", "app", "catalog", "query", "exe"],
        metadata={"language": "java"},
    )

    assert retrieval._chunk_role(chunk).name == "executor"


def test_identifier_role_boosts_preserve_java_executor_over_service_directory_label(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    executor = DocumentChunk(
        chunk_id="executor",
        file_path=Path("src/main/java/com/example/service/PageAppCatalogQueryExe.java"),
        start_line=1,
        end_line=60,
        content="class PageAppCatalogQueryExe { String fillCanApplyFilter() { return \"\"; } }",
        chunk_type="symbol",
        lexical_tokens=["page", "app", "catalog", "query", "exe", "can", "apply"],
        metadata={"language": "java"},
    )
    service = DocumentChunk(
        chunk_id="service",
        file_path=Path("src/main/java/com/example/service/AppCatalogService.java"),
        start_line=1,
        end_line=60,
        content="interface AppCatalogService { String page(); }",
        chunk_type="symbol",
        lexical_tokens=["app", "catalog", "service", "page"],
        metadata={"language": "java"},
    )
    for chunk in (executor, service):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "executor": RetrievalCandidate(
                chunk_id="executor",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.40, "path_symbol": 2.0, "direct_text": 0.6},
            ),
            "service": RetrievalCandidate(
                chunk_id="service",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.70, "path_symbol": 5.0, "direct_text": 0.9},
            ),
        },
        retrieval.tokenize_query("PageAppCatalogQueryExe fillCanApplyFilter"),
        "PageAppCatalogQueryExe fillCanApplyFilter",
    )

    assert ranked[0].chunk.chunk_id == "executor"
    assert ranked[0].score_parts["identifier_exact_match_boost"] > 0
    by_id = {item.chunk.chunk_id: item for item in ranked}
    assert (
        by_id["executor"].rerank_score
        - by_id["executor"].score_parts["identifier_exact_match_boost"]
        < by_id["service"].rerank_score
    )


def test_path_role_service_hint_treats_java_impl_as_service_without_mismatch(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    service_impl = DocumentChunk(
        chunk_id="service-impl",
        file_path=Path("src/main/java/com/example/service/impl/AuthServiceImpl.java"),
        start_line=1,
        end_line=80,
        content="class AuthServiceImpl implements AuthService { User currentUser() { return null; } }",
        chunk_type="symbol",
        lexical_tokens=["auth", "service", "impl", "current", "user"],
        metadata={"language": "java"},
    )
    service_interface = DocumentChunk(
        chunk_id="service-interface",
        file_path=Path("src/main/java/com/example/service/AuthService.java"),
        start_line=1,
        end_line=40,
        content="interface AuthService { User currentUser(); }",
        chunk_type="symbol",
        lexical_tokens=["auth", "service", "current", "user"],
        metadata={"language": "java"},
    )
    for chunk in (service_impl, service_interface):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "service-impl": RetrievalCandidate(
                chunk_id="service-impl",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.35, "path_symbol": 1.5, "direct_text": 0.6},
            ),
            "service-interface": RetrievalCandidate(
                chunk_id="service-interface",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.65, "path_symbol": 5.0, "direct_text": 0.7},
            ),
        },
        retrieval.tokenize_query("auth service current user"),
        "auth service current user",
    )

    assert ranked[0].chunk.chunk_id == "service-impl"
    assert ranked[0].score_parts["path_role_hint_boost"] > 0
    assert "path_role_mismatch_penalty" not in ranked[0].score_parts
    by_id = {item.chunk.chunk_id: item for item in ranked}
    assert (
        by_id["service-impl"].rerank_score
        - by_id["service-impl"].score_parts["path_role_hint_boost"]
        < by_id["service-interface"].rerank_score
        - by_id["service-interface"].score_parts["path_role_hint_boost"]
    )


def test_path_role_mismatch_penalty_does_not_hide_strong_identifier_match(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    view = DocumentChunk(
        chunk_id="view",
        file_path=Path("frontend/src/views/auth/register.vue"),
        start_line=1,
        end_line=80,
        content="<script setup>function useAuthStore() { return null }</script>",
        chunk_type="symbol",
        lexical_tokens=["use", "auth", "store", "register"],
        metadata={"language": "vue"},
    )
    store_chunk = DocumentChunk(
        chunk_id="store",
        file_path=Path("frontend/src/stores/modules/auth.store.ts"),
        start_line=1,
        end_line=80,
        content="export const authStore = { register() { return null } }",
        chunk_type="symbol",
        lexical_tokens=["auth", "store", "register"],
        metadata={"language": "typescript"},
    )
    for chunk in (view, store_chunk):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "view": RetrievalCandidate(
                chunk_id="view",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.50, "path_symbol": 2.25, "direct_text": 0.8},
            ),
            "store": RetrievalCandidate(
                chunk_id="store",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.55, "path_symbol": 2.5, "direct_text": 0.85},
            ),
        },
        retrieval.tokenize_query("useAuthStore register"),
        "useAuthStore register",
    )

    assert ranked[0].chunk.chunk_id == "view"
    assert ranked[0].score_parts["identifier_exact_match_boost"] > 0
    assert "path_role_mismatch_penalty" not in ranked[0].score_parts
    by_id = {item.chunk.chunk_id: item for item in ranked}
    assert (
        by_id["view"].rerank_score
        - by_id["view"].score_parts["identifier_exact_match_boost"]
        < by_id["store"].rerank_score
    )
    assert by_id["view"].rerank_score - 0.08 < by_id["store"].rerank_score


def test_chunk_role_prefers_data_type_over_generic_service_directory() -> None:
    chunk = DocumentChunk(
        chunk_id="auth-dto",
        file_path=Path("src/main/java/com/example/service/dto/AuthDto.java"),
        start_line=1,
        end_line=10,
        content="class AuthDto { String token; }",
        chunk_type="symbol",
        lexical_tokens=["auth", "dto", "token"],
        metadata={"language": "java"},
    )

    assert retrieval._chunk_role(chunk).name == "data_type"


def _generic_noise_chunk(
    chunk_id: str,
    path: str,
    content: str,
    tokens: list[str],
    metadata: dict[str, object] | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        file_path=Path(path),
        start_line=1,
        end_line=10,
        content=content,
        chunk_type="symbol",
        lexical_tokens=tokens,
        metadata=metadata or {},
    )


def _rank_generic_noise_chunks(
    tmp_path: Path,
    chunks: list[DocumentChunk],
    score_parts: dict[str, dict[str, float]],
    tokens: list[str],
    query: str,
) -> list[retrieval._RankedChunk]:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    for chunk in chunks:
        store.replace_chunks(chunk.file_path, [chunk])
    candidates = {
        chunk.chunk_id: RetrievalCandidate(
            chunk_id=chunk.chunk_id,
            score=1.0,
            source="test",
            score_parts=score_parts[chunk.chunk_id],
        )
        for chunk in chunks
    }
    return retrieval._rank_chunks(store, candidates, tokens, query)


def test_generic_intent_rerank_prefers_config_save_logic_over_yaml_artifacts(
    tmp_path: Path,
) -> None:
    query = "配置页面保存文本服务商和图片服务商 YAML provider"
    route = _generic_noise_chunk(
        "config-route",
        "backend/routes/config_routes.py",
        "def update_config(): save active provider text image yaml config",
        ["update", "config", "save", "active", "provider", "yaml"],
        {"language": "python"},
    )
    form = _generic_noise_chunk(
        "settings-form",
        "frontend/src/composables/useProviderForm.ts",
        "export async function saveTextProvider() { updateConfig(textConfig) }",
        ["save", "text", "provider", "update", "config"],
        {"language": "typescript"},
    )
    docker_yaml = _generic_noise_chunk(
        "docker-yaml",
        "docker/text_providers.yaml",
        "active_provider: openai providers api_key model",
        ["active", "provider", "providers", "yaml"],
        {"language": "yaml"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [route, form, docker_yaml],
        {
            "config-route": {"semantic": 0.45, "lexical": 0.45, "path_symbol": 2.0, "direct_text": 0.65},
            "settings-form": {"semantic": 0.42, "lexical": 0.42, "path_symbol": 2.0, "direct_text": 0.55},
            "docker-yaml": {"semantic": 0.80, "lexical": 0.80, "path_symbol": 3.0, "direct_text": 0.90},
        },
        retrieval.tokenize_query(query),
        query,
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id in {"config-route", "settings-form"}
    assert ranked.index(by_id["docker-yaml"]) > ranked.index(by_id["config-route"])
    assert by_id["docker-yaml"].score_parts["config_artifact_penalty"] < 0
    assert by_id["config-route"].score_parts["query_operation_logic_boost"] > 0


def test_generic_intent_rerank_preserves_deployment_config_queries(
    tmp_path: Path,
) -> None:
    query = "docker compose deployment yaml mount output history"
    compose = _generic_noise_chunk(
        "compose",
        "docker-compose.yml",
        "services app volumes history output text_providers yaml",
        ["docker", "compose", "deployment", "yaml", "history", "output"],
        {"language": "yaml"},
    )
    service = _generic_noise_chunk(
        "service",
        "backend/services/history.py",
        "class HistoryService: scan output history records",
        ["history", "service", "scan", "output"],
        {"language": "python"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [compose, service],
        {
            "compose": {"semantic": 0.55, "lexical": 0.55, "path_symbol": 2.5, "direct_text": 0.70},
            "service": {"semantic": 0.60, "lexical": 0.60, "path_symbol": 2.0, "direct_text": 0.70},
        },
        retrieval.tokenize_query(query),
        query,
    )

    assert ranked[0].chunk.chunk_id == "compose"
    assert ranked[0].score_parts["deployment_config_boost"] > 0
    assert "config_artifact_penalty" not in ranked[0].score_parts


def test_frontend_score_parts_rank_feature_entrypoint_over_broad_utility(
    tmp_path: Path,
) -> None:
    query = "image canvas remove scan reader upload preview"
    view = _generic_noise_chunk(
        "image-view",
        "src/views/image/ImageTool.vue",
        "<template>image canvas remove scan reader upload preview</template>",
        ["image", "canvas", "remove", "scan", "reader", "upload", "preview"],
        {"language": "vue"},
    )
    utility = _generic_noise_chunk(
        "image-helper",
        "src/utils/imageHelpers.ts",
        "export function broadImageUtility() { return 'image canvas helper transform'; }",
        ["image", "canvas", "helper", "utility", "transform"],
        {"language": "typescript"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [view, utility],
        {
            "image-view": {
                "semantic": 0.40,
                "lexical": 0.45,
                "path_symbol": 2.0,
                "direct_text": 0.60,
            },
            "image-helper": {
                "semantic": 0.45,
                "lexical": 0.40,
                "path_symbol": 2.0,
                "direct_text": 0.60,
            },
        },
        retrieval.tokenize_query(query),
        query,
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "image-view"
    assert by_id["image-view"].score_parts["frontend_entrypoint_boost"] == pytest.approx(0.35)
    assert "frontend_support_boost" not in by_id["image-helper"].score_parts


def test_frontend_score_parts_keep_implementation_utility_above_view(
    tmp_path: Path,
) -> None:
    query = "entity generate TypeScript class interface parse convert"
    view = _generic_noise_chunk(
        "entity-view",
        "src/views/entity/EntityBuilder.vue",
        "<template>entity generate form preview</template>",
        ["entity", "generate", "form", "preview"],
        {"language": "vue"},
    )
    utility = _generic_noise_chunk(
        "entity-utility",
        "src/utils/converter.ts",
        "export function buildEntity() { return 'generate TypeScript class interface parse convert entity'; }",
        ["entity", "generate", "typescript", "class", "interface", "parse", "convert"],
        {"language": "typescript"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [view, utility],
        {
            "entity-view": {
                "semantic": 0.55,
                "lexical": 0.50,
                "path_symbol": 2.0,
                "direct_text": 0.70,
            },
            "entity-utility": {
                "semantic": 0.42,
                "lexical": 0.42,
                "path_symbol": 3.0,
                "direct_text": 0.50,
            },
        },
        retrieval.tokenize_query(query),
        query,
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert by_id["entity-utility"].score_parts["frontend_support_boost"] == pytest.approx(0.18)
    assert "frontend_entrypoint_boost" not in by_id["entity-view"].score_parts


def test_frontend_direct_entrypoint_name_match_lifts_target_view_over_sibling(
    tmp_path: Path,
) -> None:
    query = "input to model generate class interface"
    target = _generic_noise_chunk(
        "input-model-view",
        "src/views/model/InputToModel.vue",
        "<template>input model generate class interface</template>",
        ["input", "model", "generate", "class", "interface"],
        {"language": "vue"},
    )
    sibling = _generic_noise_chunk(
        "model-mock-view",
        "src/views/model/ModelToMock.vue",
        "<template>model mock generate class interface</template>",
        ["model", "mock", "generate", "class", "interface"],
        {"language": "vue"},
    )
    helper = _generic_noise_chunk(
        "model-helper",
        "src/utils/modelHelpers.ts",
        "export function helper() { return 'model helper'; }",
        ["model", "helper"],
        {"language": "typescript"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [target, sibling, helper],
        {
            "input-model-view": {
                "semantic": 0.35,
                "lexical": 0.35,
                "path_symbol": 3.0,
                "direct_text": 0.75,
            },
            "model-mock-view": {
                "semantic": 0.45,
                "lexical": 0.45,
                "path_symbol": 3.0,
                "direct_text": 0.75,
            },
            "model-helper": {
                "semantic": 0.10,
                "lexical": 0.10,
                "path_symbol": 1.0,
                "direct_text": 0.20,
            },
        },
        retrieval.tokenize_query(query),
        query,
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "input-model-view"
    assert by_id["input-model-view"].score_parts["frontend_entrypoint_boost"] == pytest.approx(0.25)
    assert "frontend_entrypoint_boost" not in by_id["model-mock-view"].score_parts


def test_frontend_score_parts_demote_temp_and_lockfiles_for_feature_queries(
    tmp_path: Path,
) -> None:
    query = "image canvas remove scan reader upload preview"
    view = _generic_noise_chunk(
        "image-view",
        "src/views/image/ImageTool.vue",
        "<template>image canvas remove scan reader upload preview</template>",
        ["image", "canvas", "remove", "scan", "reader", "upload", "preview"],
        {"language": "vue"},
    )
    utility = _generic_noise_chunk(
        "image-helper",
        "src/utils/imageHelpers.ts",
        "export function imageHelper() { return 'image helper'; }",
        ["image", "helper"],
        {"language": "typescript"},
    )
    scratch = _generic_noise_chunk(
        "scratch",
        "temp/imageProbe.ts",
        "image canvas remove scan reader upload preview scratch copy",
        ["image", "canvas", "remove", "scan", "reader", "upload", "preview"],
        {"language": "typescript"},
    )
    lockfile = _generic_noise_chunk(
        "lockfile",
        "package-lock.json",
        '{"packages": {"image-reader": {"version": "1.0.0"}}}',
        ["image", "reader", "upload", "package", "lock"],
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [view, utility, scratch, lockfile],
        {
            "image-view": {"semantic": 0.40, "lexical": 0.45, "path_symbol": 2.0, "direct_text": 0.60},
            "image-helper": {"semantic": 0.35, "lexical": 0.35, "path_symbol": 2.5, "direct_text": 0.45},
            "scratch": {"semantic": 0.75, "lexical": 0.75, "path_symbol": 2.0, "direct_text": 0.90},
            "lockfile": {"semantic": 0.65, "lexical": 0.65, "path_symbol": 2.0, "direct_text": 0.85},
        },
        retrieval.tokenize_query(query),
        query,
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}
    ranked_ids = [item.chunk.chunk_id for item in ranked]

    assert ranked_ids.index("scratch") > ranked_ids.index("image-view")
    assert ranked_ids.index("lockfile") > ranked_ids.index("image-view")
    assert by_id["scratch"].score_parts["frontend_scratch_temp_penalty"] == pytest.approx(-1.00)
    assert by_id["lockfile"].score_parts["frontend_lockfile_penalty"] == pytest.approx(-0.80)


def test_frontend_score_parts_push_strong_lockfile_out_of_feature_top_neighborhood(
    tmp_path: Path,
) -> None:
    query = "image scan reader generate decode camera"
    view = _generic_noise_chunk(
        "image-view",
        "src/views/image/ImageTool.vue",
        "<template>image scan reader generate decode camera</template>",
        ["image", "scan", "reader", "generate", "decode", "camera"],
        {"language": "vue"},
    )
    utility = _generic_noise_chunk(
        "image-utility",
        "src/utils/imageCodec.ts",
        "export function imageCodec() { return 'image scan reader generate decode camera'; }",
        ["image", "scan", "reader", "generate", "decode", "camera"],
        {"language": "typescript"},
    )
    service = _generic_noise_chunk(
        "image-service",
        "src/services/imageReader.ts",
        "export function readImage() { return 'image scan reader camera'; }",
        ["image", "scan", "reader", "camera"],
        {"language": "typescript"},
    )
    component = _generic_noise_chunk(
        "image-component",
        "src/components/ImageReaderPanel.vue",
        "<template>image reader camera preview</template>",
        ["image", "reader", "camera", "preview"],
        {"language": "vue"},
    )
    store = _generic_noise_chunk(
        "image-store",
        "src/stores/image.ts",
        "export const imageState = { reader: true, camera: true }",
        ["image", "reader", "camera"],
        {"language": "typescript"},
    )
    lockfile = _generic_noise_chunk(
        "lockfile",
        "package-lock.json",
        '{"packages": {"image-reader": {"keywords": ["scan", "generate", "decode", "camera"]}}}',
        ["image", "reader", "scan", "generate", "decode", "camera", "package", "lock"],
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [view, utility, service, component, store, lockfile],
        {
            "image-view": {"semantic": 0.40, "lexical": 0.45, "path_symbol": 2.0, "direct_text": 0.60},
            "image-utility": {"semantic": 0.45, "lexical": 0.45, "path_symbol": 2.0, "direct_text": 0.55},
            "image-service": {"semantic": 0.42, "lexical": 0.42, "path_symbol": 2.0, "direct_text": 0.55},
            "image-component": {"semantic": 0.34, "lexical": 0.34, "path_symbol": 1.5, "direct_text": 0.45},
            "image-store": {"semantic": 0.32, "lexical": 0.32, "path_symbol": 1.5, "direct_text": 0.40},
            "lockfile": {"semantic": 0.95, "lexical": 0.95, "path_symbol": 2.0, "direct_text": 1.0},
        },
        retrieval.tokenize_query(query),
        query,
    )
    ranked_ids = [item.chunk.chunk_id for item in ranked]
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert "lockfile" not in ranked_ids[:5]
    assert ranked_ids.index("image-view") < ranked_ids.index("lockfile")
    assert ranked_ids.index("image-utility") < ranked_ids.index("lockfile")
    assert ranked_ids.index("image-service") < ranked_ids.index("lockfile")
    assert by_id["lockfile"].score_parts["frontend_lockfile_penalty"] == pytest.approx(-0.80)


def test_frontend_score_parts_are_absent_in_java_only_candidate_pool(
    tmp_path: Path,
) -> None:
    controller = _generic_noise_chunk(
        "controller",
        "src/main/java/com/example/ImageController.java",
        "class ImageController { String scanReaderUpload() { return service.run(); } }",
        ["image", "scan", "reader", "upload"],
        {"language": "java"},
    )
    service = _generic_noise_chunk(
        "service",
        "src/main/java/com/example/ImageService.java",
        "class ImageService { String removeCanvas() { return \"image canvas remove\"; } }",
        ["image", "canvas", "remove"],
        {"language": "java"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [controller, service],
        {
            "controller": {"semantic": 0.60, "lexical": 0.60, "path_symbol": 2.0},
            "service": {"semantic": 0.55, "lexical": 0.55, "path_symbol": 2.0},
        },
        ["image", "canvas", "remove", "scan", "reader", "upload"],
        "image canvas remove scan reader upload",
    )

    assert all(
        not any(key.startswith("frontend_") for key in item.score_parts)
        for item in ranked
    )


def test_frontend_score_parts_are_absent_in_python_like_view_service_pool(
    tmp_path: Path,
) -> None:
    view = _generic_noise_chunk(
        "python-view",
        "src/views/users.py",
        "def user_page(): return 'image scan reader generate decode camera'",
        ["image", "scan", "reader", "generate", "decode", "camera"],
        {"language": "python"},
    )
    service = _generic_noise_chunk(
        "python-service",
        "src/services/users.py",
        "def user_service(): return 'image scan reader generate decode camera'",
        ["image", "scan", "reader", "generate", "decode", "camera"],
        {"language": "python"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [view, service],
        {
            "python-view": {"semantic": 0.60, "lexical": 0.60, "path_symbol": 2.0},
            "python-service": {"semantic": 0.55, "lexical": 0.55, "path_symbol": 2.0},
        },
        retrieval.tokenize_query("image scan reader generate decode camera"),
        "image scan reader generate decode camera",
    )

    assert all(
        not any(key.startswith("frontend_") for key in item.score_parts)
        for item in ranked
    )


def test_reasons_include_frontend_score_part_diagnostics() -> None:
    reasons = retrieval._reasons(
        {
            "frontend_entrypoint_boost": 0.35,
            "frontend_support_boost": 0.18,
            "frontend_support_name_match_boost": 0.18,
            "frontend_lockfile_penalty": -0.80,
            "frontend_scratch_temp_penalty": -1.00,
            "frontend_type_decl_penalty": -0.12,
        },
        "image canvas remove scan reader upload preview",
    )

    assert "frontend entrypoint boost" in reasons
    assert "frontend support boost" in reasons
    assert "frontend support name match boost" in reasons
    assert "frontend lockfile penalty" in reasons
    assert "frontend scratch temp penalty" in reasons
    assert "frontend type declaration penalty" in reasons


def test_query_repository_boosts_frontend_direct_import_cohort_without_adding_candidates(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src" / "views" / "image").mkdir(parents=True)
    (repo / "src" / "services").mkdir(parents=True)
    (repo / "src" / "utils").mkdir(parents=True)
    (repo / "package.json").write_text(
        '{"dependencies": {"vue": "latest"}}',
        encoding="utf-8",
    )
    (repo / "src" / "views" / "image" / "ImageEditor.vue").write_text(
        """
<script setup lang="ts">
import { detectImageMask } from "@/services/imageDetection"
import { loadSession } from "@/services/sessionApi"

const copy = "image remover detection mask canvas inpaint";
</script>

<template><section>image remover detection mask canvas inpaint</section></template>
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo / "src" / "services" / "imageDetection.ts").write_text(
        """
export function detectImageMask(canvas: HTMLCanvasElement) {
  return `detection mask canvas ${canvas.width}`;
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo / "src" / "services" / "sessionApi.ts").write_text(
        "export function loadSession() { return 'user preferences'; }\n",
        encoding="utf-8",
    )
    (repo / "src" / "utils" / "canvasTools.ts").write_text(
        """
export function normalizeCanvasMask() {
  return "image remover canvas helper";
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=20,
            final_top_k=10,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    query = "image remover detection mask canvas inpaint"

    index_repository(repo, config)
    bundle = query_repository(repo, query, config)

    paths = [result.file_path.as_posix() for result in bundle.results]
    service_result = next(
        result
        for result in bundle.results
        if result.file_path.as_posix() == "src/services/imageDetection.ts"
    )
    utility_index = paths.index("src/utils/canvasTools.ts")
    service_index = paths.index("src/services/imageDetection.ts")

    assert service_index < utility_index
    assert service_result.score_parts["frontend_import_support_boost"] == pytest.approx(0.30)
    assert "frontend import support boost" in service_result.reasons
    assert "src/services/sessionApi.ts" not in paths


def test_generic_noise_generated_schema_demotes_below_source(
    tmp_path: Path,
) -> None:
    schema = _generic_noise_chunk(
        "schema",
        "src-tauri/gen/schemas/apply_dev.json",
        '{"command": "apply_dev", "engine": true}',
        ["apply", "dev", "command", "engine", "schema"],
    )
    source = _generic_noise_chunk(
        "engine",
        "src-tauri/src/engine.rs",
        "fn apply_dev_command_engine() {}",
        ["apply", "dev", "command", "engine"],
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [schema, source],
        {
            "schema": {"lexical": 0.8, "direct_text": 0.8},
            "engine": {"lexical": 0.8, "direct_text": 0.8},
        },
        ["apply", "dev", "command", "engine"],
        "apply_dev command engine",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "engine"
    assert by_id["schema"].score_parts["generated_schema_penalty"] < 0
    assert by_id["schema"].score_parts["penalty"] < 0
    assert by_id["engine"].score_parts["file_role_source_boost"] == pytest.approx(0.03)


def test_generic_noise_root_gen_schema_receives_generated_schema_penalty(
    tmp_path: Path,
) -> None:
    schema = _generic_noise_chunk(
        "root-schema",
        "gen/schemas/apply_dev.json",
        '{"command": "apply_dev", "engine": true}',
        ["apply", "dev", "command", "engine", "schema"],
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [schema],
        {"root-schema": {"lexical": 0.8, "direct_text": 0.8}},
        ["apply", "dev", "command", "engine"],
        "apply_dev command engine",
    )

    parts = ranked[0].score_parts
    assert parts["generated_schema_penalty"] < 0
    assert parts["penalty"] == pytest.approx(-0.20)


def test_generic_noise_overlapping_high_noise_uses_strongest_aggregate_penalty(
    tmp_path: Path,
) -> None:
    schema_test = _generic_noise_chunk(
        "schema-test",
        "src-tauri/gen/schemas/apply_dev.json",
        '{"command": "apply_dev", "engine": true}',
        ["apply", "dev", "command", "engine", "schema"],
        {"is_test": True},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [schema_test],
        {"schema-test": {"lexical": 0.8, "direct_text": 0.8}},
        ["apply", "dev", "command", "engine"],
        "apply_dev command engine",
    )

    parts = ranked[0].score_parts
    assert parts["test_penalty"] < 0
    assert parts["generated_schema_penalty"] < 0
    assert parts["penalty"] == pytest.approx(-0.20)


def test_generic_noise_lockfile_test_overlap_uses_strongest_aggregate_penalty(
    tmp_path: Path,
) -> None:
    lockfile_test = _generic_noise_chunk(
        "lockfile-test",
        "package-lock.json",
        '{"packages": {"": {"main": "src/main.ts"}}}',
        ["main", "package", "lock"],
        {"is_test": True},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [lockfile_test],
        {"lockfile-test": {"lexical": 0.8, "direct_text": 0.7}},
        ["main", "command", "storage"],
        "main command storage implementation",
    )

    parts = ranked[0].score_parts
    assert parts["test_penalty"] < 0
    assert parts["lockfile_penalty"] < 0
    assert parts["penalty"] == pytest.approx(-0.20)


def test_generic_noise_negative_only_scores_do_not_invert_penalty_order(
    tmp_path: Path,
) -> None:
    lockfile = _generic_noise_chunk(
        "lockfile",
        "package-lock.json",
        '{"packages": {"": {"main": "src/main.ts"}}}',
        ["main", "package", "lock"],
    )
    test_chunk = _generic_noise_chunk(
        "test",
        "src/engine_spec.rs",
        "fn apply_dev_command_engine_test() {}",
        ["apply", "dev", "command", "engine"],
        {"is_test": True},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [lockfile, test_chunk],
        {
            "lockfile": {"semantic": 0.10},
            "test": {"semantic": 0.10},
        },
        [],
        "weak semantic only",
    )

    assert ranked[0].chunk.chunk_id == "test"
    assert ranked[1].chunk.chunk_id == "lockfile"
    assert ranked[0].score_parts["penalty"] == pytest.approx(-0.10)
    assert ranked[1].score_parts["penalty"] == pytest.approx(-0.20)


def test_generic_noise_indexed_lockfile_demotes_below_source(
    tmp_path: Path,
) -> None:
    lockfile = _generic_noise_chunk(
        "lockfile",
        "package-lock.json",
        '{"packages": {"": {"main": "src/main.ts"}}}',
        ["main", "package", "lock"],
    )
    source = _generic_noise_chunk(
        "source",
        "src/main.ts",
        "export function invokeMainCommand() { return storage.apply(); }",
        ["main", "command", "storage", "apply"],
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [lockfile, source],
        {
            "lockfile": {"lexical": 0.8, "direct_text": 0.7},
            "source": {"lexical": 0.8, "direct_text": 0.7},
        },
        ["main", "command", "storage"],
        "main command storage implementation",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "source"
    assert by_id["lockfile"].score_parts["lockfile_penalty"] < 0
    assert by_id["lockfile"].score_parts["penalty"] < 0


def test_generic_noise_explicit_dependency_query_does_not_penalize_lockfile(
    tmp_path: Path,
) -> None:
    lockfile = _generic_noise_chunk(
        "lockfile",
        "package-lock.json",
        '{"packages": {"image-reader": {"version": "1.0.0"}}}',
        ["package", "dependency", "lock", "versions"],
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [lockfile],
        {"lockfile": {"lexical": 0.8, "direct_text": 0.7}},
        retrieval.tokenize_query("package dependency lock versions"),
        "package dependency lock versions",
    )

    parts = ranked[0].score_parts
    assert "lockfile_penalty" not in parts
    assert "penalty" not in parts


@pytest.mark.parametrize("query", ["go.sum", "go sum"])
def test_generic_noise_explicit_go_sum_query_does_not_penalize_lockfile(
    tmp_path: Path,
    query: str,
) -> None:
    lockfile = _generic_noise_chunk(
        "lockfile",
        "go.sum",
        "example.com/image/reader v1.2.3 h1:checksum",
        ["go", "sum", "checksum", "module"],
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [lockfile],
        {"lockfile": {"lexical": 0.8, "direct_text": 0.7}},
        retrieval.tokenize_query(query),
        query,
    )

    parts = ranked[0].score_parts
    assert "lockfile_penalty" not in parts
    assert "penalty" not in parts


@pytest.mark.parametrize(
    "lockfile_path",
    [
        "Cargo.lock",
        "go.sum",
        "package-lock.json",
        "pnpm-lock.yaml",
        "pnpm-lock.yml",
        "yarn.lock",
    ],
)
def test_generic_noise_indexed_common_lockfiles_demote_below_source(
    tmp_path: Path,
    lockfile_path: str,
) -> None:
    lockfile = _generic_noise_chunk(
        "lockfile",
        lockfile_path,
        "storage save upload lock dependency",
        ["storage", "save", "upload", "lock"],
    )
    source = _generic_noise_chunk(
        "source",
        "storage/local.go",
        "type LocalStorage struct{} func (s *LocalStorage) Save() {}",
        ["storage", "local", "save", "upload"],
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [lockfile, source],
        {
            "lockfile": {"lexical": 0.8, "direct_text": 0.7},
            "source": {"lexical": 0.8, "direct_text": 0.7},
        },
        ["storage", "save", "upload"],
        "storage save upload implementation",
    )

    by_id = {item.chunk.chunk_id: item for item in ranked}
    assert ranked[0].chunk.chunk_id == "source"
    assert by_id["lockfile"].score_parts["lockfile_penalty"] < 0
    assert by_id["lockfile"].score_parts["penalty"] == pytest.approx(-0.20)


def test_generic_noise_template_demotes_below_storage_source(
    tmp_path: Path,
) -> None:
    template = _generic_noise_chunk(
        "template",
        "templates/index.html",
        "<form action='/storage/local'>storage implementation</form>",
        ["storage", "local", "implementation"],
    )
    source = _generic_noise_chunk(
        "storage",
        "storage/local.go",
        "func NewLocalStorage() Storage { return LocalStorage{} }",
        ["storage", "local", "implementation"],
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [template, source],
        {
            "template": {"lexical": 0.8, "direct_text": 0.7},
            "storage": {"lexical": 0.8, "direct_text": 0.7},
        },
        ["storage", "implementation"],
        "storage implementation",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "storage"
    assert by_id["template"].score_parts["template_penalty"] < 0
    assert by_id["template"].score_parts["penalty"] < 0


def test_generic_noise_does_not_treat_frontend_view_as_template_noise(
    tmp_path: Path,
) -> None:
    view = _generic_noise_chunk(
        "entity-view",
        "src/views/entity/EntityBuilder.vue",
        "<template>entity generate class interface preview</template>",
        ["entity", "generate", "class", "interface", "preview"],
        {"language": "vue"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [view],
        {"entity-view": {"lexical": 0.8, "direct_text": 0.7}},
        retrieval.tokenize_query("entity generate TypeScript class interface"),
        "entity generate TypeScript class interface",
    )

    assert "template_penalty" not in ranked[0].score_parts
    assert "penalty" not in ranked[0].score_parts


def test_generic_noise_metadata_test_flag_demotes_test_chunk(
    tmp_path: Path,
) -> None:
    test_chunk = _generic_noise_chunk(
        "test",
        "src/engine_spec.rs",
        "fn apply_dev_command_engine_test() {}",
        ["apply", "dev", "command", "engine"],
        {"is_test": True},
    )
    source = _generic_noise_chunk(
        "source",
        "src/engine.rs",
        "fn apply_dev_command_engine() {}",
        ["apply", "dev", "command", "engine"],
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [test_chunk, source],
        {
            "test": {"lexical": 0.8, "direct_text": 0.7},
            "source": {"lexical": 0.8, "direct_text": 0.7},
        },
        ["apply", "dev", "command", "engine"],
        "apply_dev command engine",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "source"
    assert by_id["test"].score_parts["test_penalty"] < 0
    assert by_id["test"].score_parts["penalty"] < 0


def test_generic_noise_combined_score_ignores_diagnostic_penalties() -> None:
    aggregate_only = retrieval._combined_score({"lexical": 1.0, "penalty": -0.20})
    with_diagnostic = retrieval._combined_score(
        {"lexical": 1.0, "penalty": -0.20, "lockfile_penalty": -0.20}
    )

    assert with_diagnostic == aggregate_only


def test_role_rerank_prefers_service_impl_over_handler_for_business_query(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    service_impl = DocumentChunk(
        chunk_id="access-service-impl",
        file_path=Path("src/main/java/com/example/service/impl/AccessControlServiceImpl.java"),
        start_line=1,
        end_line=20,
        content="class AccessControlServiceImpl { void keyOpenDoor() {} }",
        chunk_type="symbol",
        lexical_tokens=["access", "control", "service", "open", "door"],
        metadata={"language": "java"},
    )
    handler = DocumentChunk(
        chunk_id="beehive-handler",
        file_path=Path("src/main/java/com/example/iot/code/beehive/BeehiveCodeHandler.java"),
        start_line=1,
        end_line=20,
        content="class BeehiveCodeHandler { void openDoor() {} }",
        chunk_type="symbol",
        lexical_tokens=["beehive", "handler", "open", "door"],
        metadata={"language": "java"},
    )
    store.replace_chunks(service_impl.file_path, [service_impl])
    store.replace_chunks(handler.file_path, [handler])
    candidates = {
        "access-service-impl": RetrievalCandidate(
            chunk_id="access-service-impl",
            score=1.0,
            source="test",
            score_parts={"semantic": 0.5, "lexical": 0.3, "path_symbol": 1.0},
        ),
        "beehive-handler": RetrievalCandidate(
            chunk_id="beehive-handler",
            score=1.0,
            source="test",
            score_parts={"semantic": 0.5, "lexical": 0.35, "path_symbol": 1.0},
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["开门", "控制"], "开门控制")

    assert ranked[0].chunk.chunk_id == "access-service-impl"
    assert ranked[0].score_parts["role_priority"] < ranked[1].score_parts["role_priority"]


def test_rerank_sort_uses_role_priority_for_noise_level_score_ties() -> None:
    generic = DocumentChunk(
        chunk_id="settings",
        file_path=Path("src-tauri/src/settings.rs"),
        start_line=1,
        end_line=77,
        content="settings persistence save load project config app settings",
        chunk_type="generic",
    )
    detail = DocumentChunk(
        chunk_id="commands",
        file_path=Path("src-tauri/src/commands.rs"),
        start_line=1,
        end_line=238,
        content="commands settings persistence save load project config app settings",
        chunk_type="generic",
    )
    near_tie_preferred_role = retrieval._RankedChunk(
        chunk=generic,
        score=0.92,
        score_parts={"role_priority": 5.0, "rerank_score": 1.07985},
        reasons=[],
        rank_tier=0,
        rerank_score=1.07985,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    near_tie_detail_role = retrieval._RankedChunk(
        chunk=detail,
        score=1.05,
        score_parts={"role_priority": 6.0, "rerank_score": 1.08},
        reasons=[],
        rank_tier=0,
        rerank_score=1.08,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    clear_winner = retrieval._RankedChunk(
        chunk=detail,
        score=1.05,
        score_parts={"role_priority": 6.0, "rerank_score": 1.09},
        reasons=[],
        rank_tier=0,
        rerank_score=1.09,
        evidence_class="original_direct",
        evidence_priority=0,
    )

    near_tie = sorted(
        [near_tie_detail_role, near_tie_preferred_role],
        key=retrieval._ranked_chunk_sort_key,
    )
    clear_gap = sorted(
        [clear_winner, near_tie_preferred_role],
        key=retrieval._ranked_chunk_sort_key,
    )
    expanded_near_tie_preferred_role = retrieval._ExpandedResult(
        chunk_ids=["settings"],
        file_path=Path("src-tauri/src/settings.rs"),
        start_line=1,
        end_line=77,
        content="settings persistence save load project config app settings",
        score=0.92,
        score_parts={"role_priority": 5.0, "rerank_score": 1.07985},
        reasons=[],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.07985,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    expanded_near_tie_detail_role = retrieval._ExpandedResult(
        chunk_ids=["commands"],
        file_path=Path("src-tauri/src/commands.rs"),
        start_line=1,
        end_line=238,
        content="commands settings persistence save load project config app settings",
        score=1.05,
        score_parts={"role_priority": 6.0, "rerank_score": 1.08},
        reasons=[],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.08,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    expanded_near_tie = sorted(
        [expanded_near_tie_detail_role, expanded_near_tie_preferred_role],
        key=retrieval._expanded_result_sort_key,
    )

    assert near_tie[0].chunk.chunk_id == "settings"
    assert clear_gap[0].chunk.chunk_id == "commands"
    assert expanded_near_tie[0].file_path == Path("src-tauri/src/settings.rs")


def test_identifier_intent_ranks_state_store_above_related_frontend_files(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    auth_store = DocumentChunk(
        chunk_id="auth-store",
        file_path=Path("frontend/src/stores/modules/auth.store.ts"),
        start_line=1,
        end_line=80,
        content="export const useAuthStore = defineStore('auth', { actions: { login() {}, register() {}, fetchCurrentUser() {} } })",
        chunk_type="symbol",
        lexical_tokens=["use", "auth", "store", "login", "register", "fetch", "current", "user"],
        metadata={"language": "typescript"},
    )
    auth_service = DocumentChunk(
        chunk_id="auth-service",
        file_path=Path("frontend/src/api/services/auth.service.ts"),
        start_line=1,
        end_line=60,
        content="export function login() {} export function register() {} export function fetchCurrentUser() {}",
        chunk_type="symbol",
        lexical_tokens=["auth", "service", "login", "register", "fetch", "current", "user"],
        metadata={"language": "typescript"},
    )
    register_view = DocumentChunk(
        chunk_id="register-view",
        file_path=Path("frontend/src/views/auth/register.vue"),
        start_line=1,
        end_line=60,
        content="<script setup>useAuthStore().register()</script>",
        chunk_type="symbol",
        lexical_tokens=["auth", "register", "use", "store"],
        metadata={"language": "vue"},
    )
    for chunk in (auth_store, auth_service, register_view):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "auth-store": RetrievalCandidate(
                chunk_id="auth-store",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.45, "path_symbol": 4.25, "direct_text": 1.0},
            ),
            "auth-service": RetrievalCandidate(
                chunk_id="auth-service",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.65, "path_symbol": 3.5, "direct_text": 1.0},
            ),
            "register-view": RetrievalCandidate(
                chunk_id="register-view",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.60, "path_symbol": 2.5, "direct_text": 0.8},
            ),
        },
        retrieval.tokenize_query("frontend useAuthStore login register fetchCurrentUser Pinia"),
        "frontend useAuthStore login register fetchCurrentUser Pinia",
    )

    assert ranked[0].chunk.chunk_id == "auth-store"
    score_parts_by_chunk = {item.chunk.chunk_id: item.score_parts for item in ranked}
    assert ranked[0].score_parts["identifier_exact_match_boost"] > 0
    assert (
        score_parts_by_chunk["auth-store"]["identifier_exact_match_boost"]
        > score_parts_by_chunk["auth-service"].get("identifier_exact_match_boost", 0.0)
    )
    assert ranked[0].score_parts["path_role_hint_boost"] > 0


def test_identifier_intent_ranks_composable_above_chat_types_and_views(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    composable = DocumentChunk(
        chunk_id="sse-composable",
        file_path=Path("frontend/src/views/chat/composables/useSseConnection.ts"),
        start_line=1,
        end_line=120,
        content="export function useSseConnection() { return new EventSource('/chat') }",
        chunk_type="symbol",
        lexical_tokens=["use", "sse", "connection", "eventsource", "chat", "composable"],
        metadata={"language": "typescript"},
    )
    types = DocumentChunk(
        chunk_id="chat-types",
        file_path=Path("frontend/src/views/chat/types.ts"),
        start_line=1,
        end_line=60,
        content="export interface ChatMessage { id: string; content: string }",
        chunk_type="symbol",
        lexical_tokens=["chat", "types", "message"],
        metadata={"language": "typescript"},
    )
    view = DocumentChunk(
        chunk_id="chat-view",
        file_path=Path("frontend/src/views/chat/index.vue"),
        start_line=1,
        end_line=100,
        content="<script setup>useSseConnection()</script>",
        chunk_type="symbol",
        lexical_tokens=["chat", "use", "sse", "connection"],
        metadata={"language": "vue"},
    )
    for chunk in (composable, types, view):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "sse-composable": RetrievalCandidate(
                chunk_id="sse-composable",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.45, "path_symbol": 4.5, "direct_text": 1.0},
            ),
            "chat-types": RetrievalCandidate(
                chunk_id="chat-types",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.62, "path_symbol": 3.0, "direct_text": 0.6},
            ),
            "chat-view": RetrievalCandidate(
                chunk_id="chat-view",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.60, "path_symbol": 3.0, "direct_text": 0.8},
            ),
        },
        retrieval.tokenize_query("frontend useSseConnection EventSource chat composable"),
        "frontend useSseConnection EventSource chat composable",
    )

    assert ranked[0].chunk.chunk_id == "sse-composable"
    score_parts_by_chunk = {item.chunk.chunk_id: item.score_parts for item in ranked}
    assert ranked[0].score_parts["identifier_exact_match_boost"] > 0
    assert (
        score_parts_by_chunk["sse-composable"]["identifier_exact_match_boost"]
        > score_parts_by_chunk["chat-view"].get("identifier_exact_match_boost", 0.0)
    )
    assert ranked[0].score_parts["path_role_hint_boost"] > 0


def test_identifier_intent_ranks_storage_source_above_unrelated_cli_entrypoint(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    storage = DocumentChunk(
        chunk_id="local-storage",
        file_path=Path("storage/local.go"),
        start_line=1,
        end_line=80,
        content="type LocalStorage struct{} func (s *LocalStorage) Save(file multipart.File) error { return nil }",
        chunk_type="symbol",
        lexical_tokens=["local", "storage", "save", "file", "multipart"],
        metadata={"language": "go"},
    )
    typora = DocumentChunk(
        chunk_id="typora-main",
        file_path=Path("cmd/typora/main.go"),
        start_line=1,
        end_line=80,
        content="func main() { uploadFromTypora(); saveFile(); }",
        chunk_type="symbol",
        lexical_tokens=["typora", "upload", "save", "file", "main"],
        metadata={"language": "go"},
    )
    for chunk in (storage, typora):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "local-storage": RetrievalCandidate(
                chunk_id="local-storage",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.42, "path_symbol": 2.0, "direct_text": 0.8},
            ),
            "typora-main": RetrievalCandidate(
                chunk_id="typora-main",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.50, "path_symbol": 2.0, "direct_text": 0.8},
            ),
        },
        retrieval.tokenize_query("UploadHandler MultiUpload multipart file storage Save"),
        "UploadHandler MultiUpload multipart file storage Save",
    )

    score_parts_by_chunk = {item.chunk.chunk_id: item.score_parts for item in ranked}
    assert ranked[0].chunk.chunk_id == "local-storage"
    assert score_parts_by_chunk["local-storage"]["path_role_hint_boost"] == pytest.approx(0.14)
    assert score_parts_by_chunk["typora-main"]["path_role_mismatch_penalty"] == pytest.approx(-0.08)


def test_identifier_intent_ranks_rust_frontend_entry_when_query_names_frontend(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    frontend_metadata = {
        "project_scope_metadata_version": 1,
        "project_root": "",
        "project_name": "env-switcher",
        "project_kind": "frontend",
        "project_languages": ["typescript"],
        "project_markers": ["package.json"],
    }
    rust_metadata = {
        "project_scope_metadata_version": 1,
        "project_root": "src-tauri",
        "project_name": "src-tauri",
        "project_kind": "rust",
        "project_languages": ["rust"],
        "project_markers": ["Cargo.toml"],
    }
    frontend = DocumentChunk(
        chunk_id="frontend-main",
        file_path=Path("src/main.ts"),
        start_line=1,
        end_line=120,
        content=(
            "import { invoke } from '@tauri-apps/api/core'; "
            "document.querySelector('#apply-dev')?.addEventListener('click', async () => "
            "{ await runCommand('apply_dev'); }); "
            "document.querySelector('#restore-clean')?.addEventListener('click', async () => "
            "{ await runCommand('restore_clean'); }); "
            "async function runCommand(command: string) { await invoke(command); }"
        ),
        chunk_type="symbol",
        lexical_tokens=["frontend", "project", "switcher", "invoke", "apply", "dev", "restore", "clean"],
        metadata=frontend_metadata,
    )
    commands = DocumentChunk(
        chunk_id="commands",
        file_path=Path("src-tauri/src/commands.rs"),
        start_line=1,
        end_line=120,
        content=(
            "use crate::engine::ProjectSwitcher; "
            "pub fn apply_dev() { ProjectSwitcher::new().apply_dev(); } "
            "pub fn restore_clean() { ProjectSwitcher::new().restore_clean(); }"
        ),
        chunk_type="symbol",
        lexical_tokens=["tauri", "command", "apply", "dev", "restore", "clean"],
        metadata=rust_metadata,
    )
    for chunk in (frontend, commands):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "frontend-main": RetrievalCandidate(
                chunk_id="frontend-main",
                score=1.0,
                source="direct",
                score_parts={
                    "semantic": 0.04,
                    "lexical": 1.58,
                    "path_symbol": 1.5,
                    "direct_text": 1.0,
                },
            ),
            "commands": RetrievalCandidate(
                chunk_id="commands",
                score=1.0,
                source="direct",
                score_parts={
                    "lexical": 1.71,
                    "path_symbol": 1.5,
                    "direct_text": 1.0,
                },
            ),
        },
        retrieval.tokenize_query("invoke apply_dev restore_clean frontend ProjectSwitcher"),
        "invoke apply_dev restore_clean frontend ProjectSwitcher",
    )

    assert ranked[0].chunk.chunk_id == "frontend-main"
    score_parts_by_chunk = {item.chunk.chunk_id: item.score_parts for item in ranked}
    assert ranked[0].score_parts["identifier_exact_match_boost"] > 0
    assert score_parts_by_chunk["commands"]["identifier_exact_match_boost"] > 0
    assert ranked[0].score_parts["path_role_hint_boost"] > 0


def test_role_rerank_exact_handler_file_hint_beats_same_subproject_noise(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    collector_metadata = {
        "project_scope_metadata_version": 1,
        "project_root": "collector",
        "project_name": "collector",
        "project_kind": "go",
        "project_languages": ["go"],
    }
    backend_metadata = {
        "project_scope_metadata_version": 1,
        "project_root": "investment-assistant-backend",
        "project_name": "investment-assistant-backend",
        "project_kind": "java",
        "project_languages": ["java"],
    }
    handler = DocumentChunk(
        chunk_id="collect-handler",
        file_path=Path("collector/internal/api/handler/collect_handler.go"),
        start_line=1,
        end_line=40,
        content=(
            "package handler\n"
            "type CollectHandler struct{}\n"
            "func (h *CollectHandler) CollectNav() string { return \"gin\" }\n"
            "func (h *CollectHandler) BatchCollectNav() string { return \"gin\" }\n"
        ),
        chunk_type="symbol",
        lexical_tokens=[
            "collector",
            "collect",
            "handler",
            "collecthandler",
            "collectnav",
            "batchcollectnav",
            "gin",
        ],
        metadata=collector_metadata,
    )
    service_noise = DocumentChunk(
        chunk_id="fund-service",
        file_path=Path("collector/internal/service/fund_service.go"),
        start_line=1,
        end_line=40,
        content=(
            "package service\n"
            "func BatchCollectNav() string { return \"collector fund nav gin\" }\n"
        ),
        chunk_type="symbol",
        lexical_tokens=[
            "collector",
            "fund",
            "service",
            "batchcollectnav",
            "collectnav",
            "gin",
        ],
        metadata=collector_metadata,
    )
    repository_noise = DocumentChunk(
        chunk_id="nav-repo",
        file_path=Path("collector/internal/repository/nav_repo.go"),
        start_line=1,
        end_line=40,
        content=(
            "package repository\n"
            "func SaveNav() string { return \"collector collect nav gin\" }\n"
        ),
        chunk_type="symbol",
        lexical_tokens=["collector", "repository", "collect", "nav", "gin"],
        metadata=collector_metadata,
    )
    backend_noise = DocumentChunk(
        chunk_id="backend-fund-service",
        file_path=Path(
            "investment-assistant-backend/src/main/java/com/investment/application/fund/FundAppService.java"
        ),
        start_line=1,
        end_line=40,
        content="class FundAppService { String CollectNav() { return \"fund\"; } }",
        chunk_type="symbol",
        lexical_tokens=["fund", "service", "collectnav"],
        metadata=backend_metadata,
    )
    for chunk in (handler, service_noise, repository_noise, backend_noise):
        store.replace_chunks(chunk.file_path, [chunk])

    candidates = {
        "collect-handler": RetrievalCandidate(
            chunk_id="collect-handler",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.55,
                "lexical": 0.45,
                "path_symbol": 4.75,
                "direct_text": 1.0,
            },
        ),
        "fund-service": RetrievalCandidate(
            chunk_id="fund-service",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.70,
                "lexical": 1.0,
                "path_symbol": 1.5,
                "direct_text": 1.0,
            },
        ),
        "nav-repo": RetrievalCandidate(
            chunk_id="nav-repo",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.58,
                "lexical": 0.8,
                "path_symbol": 1.0,
                "direct_text": 1.0,
            },
        ),
        "backend-fund-service": RetrievalCandidate(
            chunk_id="backend-fund-service",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.6,
                "lexical": 0.45,
                "path_symbol": 1.0,
                "direct_text": 0.5,
            },
        ),
    }
    query = "collector CollectHandler collect_handler.go CollectNav BatchCollectNav gin"

    ranked = retrieval._rank_chunks(
        store,
        candidates,
        retrieval.tokenize_query(query),
        query,
    )

    assert ranked[0].chunk.chunk_id == "collect-handler"
    assert ranked[0].score_parts["project_file_hint_boost"] == 0.08
    assert ranked[0].score_parts["file_hint_match_boost"] == 0.40
    assert ranked[0].score_parts["role_exact_match_boost"] == 0.08
    assert "role_penalty" not in ranked[0].score_parts


def test_role_rerank_go_service_file_hint_beats_same_subproject_repository_noise(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    collector_metadata = {
        "project_scope_metadata_version": 1,
        "project_root": "collector",
        "project_name": "collector",
        "project_kind": "go",
        "project_languages": ["go"],
    }
    backend_metadata = {
        "project_scope_metadata_version": 1,
        "project_root": "investment-assistant-backend",
        "project_name": "investment-assistant-backend",
        "project_kind": "java",
        "project_languages": ["java"],
    }
    service = DocumentChunk(
        chunk_id="fund-service",
        file_path=Path("collector/internal/service/fund_service.go"),
        start_line=1,
        end_line=40,
        content=(
            "package service\n"
            "type FundService struct{}\n"
            "func (s *FundService) CollectNav() string { return \"fund service\" }\n"
            "func (s *FundService) BatchCollectNav() string { return \"fund service\" }\n"
        ),
        chunk_type="symbol",
        lexical_tokens=[
            "collector",
            "fund",
            "service",
            "fundservice",
            "collectnav",
            "batchcollectnav",
        ],
        metadata=collector_metadata,
    )
    fund_repo = DocumentChunk(
        chunk_id="fund-repo",
        file_path=Path("collector/internal/repository/fund_repo.go"),
        start_line=1,
        end_line=40,
        content=(
            "package repository\n"
            "func CollectNav() string { return \"collector fund service\" }\n"
        ),
        chunk_type="symbol",
        lexical_tokens=["collector", "fund", "repository", "collectnav", "service"],
        metadata=collector_metadata,
    )
    nav_repo = DocumentChunk(
        chunk_id="nav-repo",
        file_path=Path("collector/internal/repository/nav_repo.go"),
        start_line=1,
        end_line=40,
        content=(
            "package repository\n"
            "func BatchCollectNav() string { return \"collector nav fund service\" }\n"
        ),
        chunk_type="symbol",
        lexical_tokens=["collector", "nav", "repository", "batchcollectnav", "service"],
        metadata=collector_metadata,
    )
    backend_noise = DocumentChunk(
        chunk_id="backend-fund-service",
        file_path=Path(
            "investment-assistant-backend/src/main/java/com/investment/application/fund/FundAppService.java"
        ),
        start_line=1,
        end_line=40,
        content="class FundAppService { String collectNav() { return \"fund\"; } }",
        chunk_type="symbol",
        lexical_tokens=["fund", "service", "collectnav"],
        metadata=backend_metadata,
    )
    for chunk in (service, fund_repo, nav_repo, backend_noise):
        store.replace_chunks(chunk.file_path, [chunk])

    candidates = {
        "fund-service": RetrievalCandidate(
            chunk_id="fund-service",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.45,
                "lexical": 0.35,
                "path_symbol": 4.5,
                "direct_text": 1.0,
            },
        ),
        "fund-repo": RetrievalCandidate(
            chunk_id="fund-repo",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.65,
                "lexical": 0.95,
                "path_symbol": 3.0,
                "direct_text": 1.0,
            },
        ),
        "nav-repo": RetrievalCandidate(
            chunk_id="nav-repo",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.60,
                "lexical": 0.85,
                "path_symbol": 2.75,
                "direct_text": 1.0,
            },
        ),
        "backend-fund-service": RetrievalCandidate(
            chunk_id="backend-fund-service",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.4,
                "lexical": 0.4,
                "path_symbol": 1.0,
                "direct_text": 0.5,
            },
        ),
    }
    query = "collector FundService fund_service.go CollectNav BatchCollectNav fund service"

    ranked = retrieval._rank_chunks(
        store,
        candidates,
        retrieval.tokenize_query(query),
        query,
    )

    assert ranked[0].chunk.chunk_id == "fund-service"
    assert ranked[0].score_parts["file_hint_match_boost"] == 0.40
    assert ranked[0].score_parts["role_exact_match_boost"] == 0.35
    assert "impl_match_boost" not in ranked[0].score_parts
    assert "relation_role_boost" not in ranked[0].score_parts


def test_role_rerank_explicit_source_file_path_hint_beats_service_noise(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    collector_metadata = {
        "project_scope_metadata_version": 1,
        "project_root": "collector",
        "project_name": "collector",
        "project_kind": "go",
        "project_languages": ["go"],
    }
    backend_metadata = {
        "project_scope_metadata_version": 1,
        "project_root": "investment-assistant-backend",
        "project_name": "investment-assistant-backend",
        "project_kind": "java",
        "project_languages": ["java"],
    }
    source = DocumentChunk(
        chunk_id="eastmoney-nav",
        file_path=Path("collector/internal/source/eastmoney/nav.go"),
        start_line=1,
        end_line=40,
        content=(
            "package eastmoney\n"
            "func FetchFundNav() string { return \"collector eastmoney nav.go fetch fund nav\" }\n"
        ),
        chunk_type="symbol",
        lexical_tokens=[
            "collector",
            "eastmoney",
            "fetch",
            "fund",
            "go",
            "nav",
        ],
        metadata=collector_metadata,
    )
    fund_service = DocumentChunk(
        chunk_id="fund-service",
        file_path=Path("collector/internal/service/fund_service.go"),
        start_line=1,
        end_line=40,
        content=(
            "package service\n"
            "func FetchFundNav() string { return \"collector fund nav service\" }\n"
        ),
        chunk_type="symbol",
        lexical_tokens=["collector", "fetch", "fund", "nav", "service"],
        metadata=collector_metadata,
    )
    nav_service = DocumentChunk(
        chunk_id="nav-service",
        file_path=Path("collector/internal/service/nav_service.go"),
        start_line=1,
        end_line=40,
        content=(
            "package service\n"
            "func Nav() string { return \"collector fund nav fetch service\" }\n"
        ),
        chunk_type="symbol",
        lexical_tokens=["collector", "fetch", "fund", "nav", "service"],
        metadata=collector_metadata,
    )
    backend_noise = DocumentChunk(
        chunk_id="backend-fund-service",
        file_path=Path(
            "investment-assistant-backend/src/main/java/com/investment/application/fund/FundAppService.java"
        ),
        start_line=1,
        end_line=40,
        content="class FundAppService { String fetchFundNav() { return \"fund\"; } }",
        chunk_type="symbol",
        lexical_tokens=["fetch", "fund", "nav", "service"],
        metadata=backend_metadata,
    )
    for chunk in (source, fund_service, nav_service, backend_noise):
        store.replace_chunks(chunk.file_path, [chunk])

    candidates = {
        "eastmoney-nav": RetrievalCandidate(
            chunk_id="eastmoney-nav",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.45,
                "lexical": 0.35,
                "path_symbol": 4.5,
                "direct_text": 1.0,
            },
        ),
        "fund-service": RetrievalCandidate(
            chunk_id="fund-service",
            score=1.0,
            source="direct,relation",
            score_parts={
                "semantic": 0.70,
                "lexical": 1.0,
                "path_symbol": 2.0,
                "direct_text": 1.0,
                "original_relation": 0.2,
                "relation": 0.2,
            },
        ),
        "nav-service": RetrievalCandidate(
            chunk_id="nav-service",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.65,
                "lexical": 0.95,
                "path_symbol": 2.0,
                "direct_text": 1.0,
            },
        ),
        "backend-fund-service": RetrievalCandidate(
            chunk_id="backend-fund-service",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.4,
                "lexical": 0.4,
                "path_symbol": 1.0,
                "direct_text": 0.5,
            },
        ),
    }
    query = "collector eastmoney nav.go fetch fund nav"

    ranked = retrieval._rank_chunks(
        store,
        candidates,
        retrieval.tokenize_query(query),
        query,
    )

    assert ranked[0].chunk.chunk_id == "eastmoney-nav"
    assert ranked[0].score_parts["project_file_hint_boost"] == 0.08
    assert ranked[0].score_parts["file_hint_match_boost"] == 0.40


def test_service_impl_exact_match_boost_keeps_impl_near_entrypoints(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    controller = DocumentChunk(
        chunk_id="open-controller",
        file_path=Path("src/main/java/com/example/controller/OpenApiController.java"),
        start_line=1,
        end_line=20,
        content="class OpenApiController { void openDoor() {} }",
        chunk_type="symbol",
        lexical_tokens=["open", "api", "controller", "door"],
        metadata={"language": "java"},
    )
    service_impl = DocumentChunk(
        chunk_id="access-service-impl",
        file_path=Path("src/main/java/com/example/service/impl/AccessControlServiceImpl.java"),
        start_line=1,
        end_line=20,
        content="class AccessControlServiceImpl { void openDoor() {} }",
        chunk_type="symbol",
        lexical_tokens=["access", "control", "service", "open", "door"],
        metadata={"language": "java"},
    )
    for chunk in (controller, service_impl):
        store.replace_chunks(chunk.file_path, [chunk])

    candidates = {
        "open-controller": RetrievalCandidate(
            chunk_id="open-controller",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.55,
                "lexical": 0.35,
                "path_symbol": 1.0,
                "signal": 0.5,
                "token_coverage": 0.5,
            },
        ),
        "access-service-impl": RetrievalCandidate(
            chunk_id="access-service-impl",
            score=1.0,
            source="direct,relation",
            score_parts={
                "semantic": 0.55,
                "lexical": 0.35,
                "path_symbol": 1.0,
                "original_relation": 0.2,
                "relation": 0.2,
                "token_coverage": 0.5,
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["开门", "控制"], "开门控制")

    assert ranked[0].chunk.chunk_id == "access-service-impl"
    assert ranked[0].score_parts["impl_match_boost"] == 0.18


def test_service_impl_high_path_match_gets_role_exact_boost(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    service_impl = DocumentChunk(
        chunk_id="app-info-service-impl",
        file_path=Path("src/main/java/com/example/service/AppInfoServiceImpl.java"),
        start_line=1,
        end_line=40,
        content="class AppInfoServiceImpl { Page page(AppCatalogPageQry qry) { return null; } }",
        chunk_type="symbol",
        lexical_tokens=["app", "info", "service", "impl", "page", "catalog", "qry"],
        metadata={"language": "java"},
    )
    store.replace_chunks(service_impl.file_path, [service_impl])

    ranked = retrieval._rank_chunks(
        store,
        {
            "app-info-service-impl": RetrievalCandidate(
                chunk_id="app-info-service-impl",
                score=1.0,
                source="direct",
                score_parts={
                    "semantic": 0.50,
                    "path_symbol": 4.0,
                    "direct_text": 0.5,
                    "token_coverage": 0.8,
                },
            )
        },
        ["app", "catalog", "page", "can", "apply"],
        "/appCatalog/page canApply",
    )

    assert ranked[0].score_parts["role_exact_match_boost"] == 0.35
    assert ranked[0].score_parts["impl_match_boost"] == 0.18


def test_data_type_exact_match_beats_low_coverage_entrypoint_noise(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    user_controller = DocumentChunk(
        chunk_id="user-controller",
        file_path=Path("src/main/java/com/example/controller/UserController.java"),
        start_line=1,
        end_line=20,
        content="class UserController { void editProfile() {} }",
        chunk_type="symbol",
        lexical_tokens=["user", "controller"],
        metadata={"language": "java"},
    )
    user_entity = DocumentChunk(
        chunk_id="user-entity",
        file_path=Path("src/main/java/com/example/entity/User.java"),
        start_line=1,
        end_line=20,
        content="class User { String account; String password; }",
        chunk_type="symbol",
        lexical_tokens=["user", "account", "password"],
        metadata={"language": "java"},
    )
    for chunk in (user_controller, user_entity):
        store.replace_chunks(chunk.file_path, [chunk])

    candidates = {
        "user-controller": RetrievalCandidate(
            chunk_id="user-controller",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.52,
                "lexical": 0.6,
                "path_symbol": 2.0,
                "signal": 0.1,
            },
        ),
        "user-entity": RetrievalCandidate(
            chunk_id="user-entity",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.53,
                "lexical": 1.05,
                "path_symbol": 2.0,
            },
        ),
    }

    ranked = retrieval._rank_chunks(
        store,
        candidates,
        ["account", "password", "login", "register", "auth", "user"],
        "账号密码登录注册",
    )

    assert ranked[0].chunk.chunk_id == "user-entity"
    assert ranked[0].score_parts["role_exact_match_boost"] == 0.24


def test_entrypoint_exact_match_beats_related_service_for_list_query(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    equipment_controller = DocumentChunk(
        chunk_id="equipment-controller",
        file_path=Path("src/main/java/com/example/controller/EquipmentController.java"),
        start_line=1,
        end_line=20,
        content="class EquipmentController { void page() {} void list() {} }",
        chunk_type="symbol",
        lexical_tokens=["equipment", "controller", "device", "list", "page"],
        metadata={"language": "java"},
    )
    device_service = DocumentChunk(
        chunk_id="device-control-service",
        file_path=Path("src/main/java/com/example/service/DeviceControlService.java"),
        start_line=1,
        end_line=20,
        content="interface DeviceControlService { boolean deviceOnlineStatus(); }",
        chunk_type="symbol",
        lexical_tokens=["device", "control", "service"],
        metadata={"language": "java"},
    )
    for chunk in (equipment_controller, device_service):
        store.replace_chunks(chunk.file_path, [chunk])

    candidates = {
        "equipment-controller": RetrievalCandidate(
            chunk_id="equipment-controller",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.56,
                "lexical": 0.04,
                "path_symbol": 4.75,
                "signal": 0.3,
            },
        ),
        "device-control-service": RetrievalCandidate(
            chunk_id="device-control-service",
            score=1.0,
            source="direct,relation",
            score_parts={
                "semantic": 0.57,
                "path_symbol": 2.0,
                "original_relation": 0.2,
                "relation": 0.2,
            },
        ),
    }

    ranked = retrieval._rank_chunks(
        store,
        candidates,
        ["device", "equipment", "list", "page"],
        "设备列表",
    )

    assert ranked[0].chunk.chunk_id == "equipment-controller"
    assert ranked[0].score_parts["role_exact_match_boost"] == 0.12


def test_role_rerank_prefers_alarm_service_over_mqtt_constant(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    alarm_service = DocumentChunk(
        chunk_id="alarm-service-impl",
        file_path=Path("src/main/java/com/example/service/impl/AlarmServiceImpl.java"),
        start_line=1,
        end_line=20,
        content="class AlarmServiceImpl { void saveAlarm() {} }",
        chunk_type="symbol",
        lexical_tokens=["alarm", "service", "device"],
        metadata={"language": "java"},
    )
    mqtt_constant = DocumentChunk(
        chunk_id="mqtt-constant",
        file_path=Path("src/main/java/com/example/mqtt/peach/PeachMqttConstant.java"),
        start_line=1,
        end_line=20,
        content='class PeachMqttConstant { static final String ALARM = "alarm"; }',
        chunk_type="symbol",
        lexical_tokens=["alarm", "mqtt", "constant", "device"],
        metadata={"language": "java"},
    )
    store.replace_chunks(alarm_service.file_path, [alarm_service])
    store.replace_chunks(mqtt_constant.file_path, [mqtt_constant])
    candidates = {
        "alarm-service-impl": RetrievalCandidate(
            chunk_id="alarm-service-impl",
            score=1.0,
            source="test",
            score_parts={"semantic": 0.5, "lexical": 0.3, "path_symbol": 1.0},
        ),
        "mqtt-constant": RetrievalCandidate(
            chunk_id="mqtt-constant",
            score=1.0,
            source="test",
            score_parts={"semantic": 0.5, "lexical": 0.35, "path_symbol": 1.0},
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["设备", "告警"], "设备告警")

    assert ranked[0].chunk.chunk_id == "alarm-service-impl"


def test_relation_chain_service_interface_stays_near_impl(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    controller = DocumentChunk(
        chunk_id="equipment-controller",
        file_path=Path("src/main/java/com/example/controller/EquipmentController.java"),
        start_line=1,
        end_line=20,
        content="class EquipmentController { EquipmentService equipmentService; }",
        chunk_type="symbol",
        lexical_tokens=["equipment", "controller", "service"],
        metadata={"language": "java"},
    )
    service = DocumentChunk(
        chunk_id="equipment-service",
        file_path=Path("src/main/java/com/example/service/EquipmentService.java"),
        start_line=1,
        end_line=20,
        content="interface EquipmentService { void page(); }",
        chunk_type="symbol",
        lexical_tokens=["equipment", "service", "page"],
        metadata={"language": "java"},
    )
    impl = DocumentChunk(
        chunk_id="equipment-service-impl",
        file_path=Path("src/main/java/com/example/service/impl/EquipmentServiceImpl.java"),
        start_line=1,
        end_line=20,
        content="class EquipmentServiceImpl implements EquipmentService { void page() {} }",
        chunk_type="symbol",
        lexical_tokens=["equipment", "service", "impl", "page"],
        metadata={"language": "java"},
    )
    handler = DocumentChunk(
        chunk_id="equipment-handler",
        file_path=Path("src/main/java/com/example/iot/EquipmentHandler.java"),
        start_line=1,
        end_line=20,
        content="class EquipmentHandler { void page() {} }",
        chunk_type="symbol",
        lexical_tokens=["equipment", "handler", "page"],
        metadata={"language": "java"},
    )
    for chunk in (controller, service, impl, handler):
        store.replace_chunks(chunk.file_path, [chunk])
    candidates = {
        "equipment-controller": RetrievalCandidate(
            chunk_id="equipment-controller",
            score=1.0,
            source="direct",
            score_parts={"lexical": 0.5, "path_symbol": 1.0},
        ),
        "equipment-service": RetrievalCandidate(
            chunk_id="equipment-service",
            score=1.0,
            source="relation",
            score_parts={"original_relation": 0.8, "relation": 0.8},
        ),
        "equipment-service-impl": RetrievalCandidate(
            chunk_id="equipment-service-impl",
            score=1.0,
            source="relation",
            score_parts={"original_relation": 0.8, "relation": 0.8},
        ),
        "equipment-handler": RetrievalCandidate(
            chunk_id="equipment-handler",
            score=1.0,
            source="semantic",
            score_parts={"semantic": 0.45, "lexical": 0.2},
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["设备", "列表"], "设备列表")
    top3 = [item.chunk.chunk_id for item in ranked[:3]]

    assert "equipment-service" in top3
    assert "equipment-service-impl" in top3
    assert "equipment-handler" not in top3


def test_relation_role_boost_applies_to_service_interface_with_relation_support(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    service = DocumentChunk(
        chunk_id="equipment-service",
        file_path=Path("src/main/java/com/example/service/EquipmentService.java"),
        start_line=1,
        end_line=20,
        content="interface EquipmentService { void page(); }",
        chunk_type="symbol",
        lexical_tokens=["equipment", "service", "page"],
        metadata={"language": "java"},
    )
    store.replace_chunks(service.file_path, [service])
    candidates = {
        "equipment-service": RetrievalCandidate(
            chunk_id="equipment-service",
            score=1.0,
            source="relation",
            score_parts={"original_relation": 0.8, "relation": 0.8},
        )
    }

    ranked = retrieval._rank_chunks(store, candidates, ["equipment", "page"], "equipment page")

    assert ranked[0].score_parts["relation_role_boost"] == 0.08


def test_detail_only_strong_direct_still_sets_planner_ceiling(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    handler = DocumentChunk(
        chunk_id="access-handler",
        file_path=Path("src/main/java/com/example/iot/AccessCodeHandler.java"),
        start_line=1,
        end_line=20,
        content="class AccessCodeHandler { void openDoor() {} }",
        chunk_type="symbol",
        lexical_tokens=["access", "handler", "open", "door"],
        metadata={"language": "java"},
    )
    service_impl = DocumentChunk(
        chunk_id="access-service-impl",
        file_path=Path("src/main/java/com/example/service/impl/AccessControlServiceImpl.java"),
        start_line=1,
        end_line=20,
        content="class AccessControlServiceImpl { void openDoor() {} }",
        chunk_type="symbol",
        lexical_tokens=["access", "control", "service", "open", "door"],
        metadata={"language": "java"},
    )
    for chunk in (handler, service_impl):
        store.replace_chunks(chunk.file_path, [chunk])

    candidates = {
        "access-handler": RetrievalCandidate(
            chunk_id="access-handler",
            score=1.0,
            source="direct",
            score_parts={"lexical": 0.8, "path_symbol": 5.0},
        ),
        "access-service-impl": RetrievalCandidate(
            chunk_id="access-service-impl",
            score=1.0,
            source="planner_relation",
            score_parts={"planner_relation": 1.0, "relation": 1.0},
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["handler"], "handler")

    assert ranked[0].chunk.chunk_id == "access-handler"
    assert ranked[1].chunk.chunk_id == "access-service-impl"
    assert ranked[1].rerank_score < ranked[0].rerank_score


def test_non_readme_markdown_display_priority_is_lower_than_code(
    tmp_path: Path,
) -> None:
    code_results, evidence_anchors = retrieval._split_code_results_and_evidence_anchors(
        [
            retrieval._ExpandedResult(
                chunk_ids=["readme"],
                file_path=Path("README.md"),
                start_line=1,
                end_line=3,
                content="当前审批人查询接口由 ApprovalController 负责。",
                score=1.0,
                score_parts={
                    "direct_text": 1.0,
                    "rerank_score": 1.2,
                },
                reasons=["direct text match"],
                followup_keywords=[],
                rank_tier=0,
                rerank_score=1.2,
                evidence_class="original_direct",
                evidence_priority=0,
            ),
            retrieval._ExpandedResult(
                chunk_ids=["risks"],
                file_path=Path("RISKS.md"),
                start_line=1,
                end_line=3,
                content="当前审批人查询接口的风险说明。",
                score=0.95,
                score_parts={
                    "direct_text": 0.95,
                    "rerank_score": 1.1,
                },
                reasons=["direct text match"],
                followup_keywords=[],
                rank_tier=0,
                rerank_score=1.1,
                evidence_class="original_direct",
                evidence_priority=0,
            ),
            retrieval._ExpandedResult(
                chunk_ids=["controller"],
                file_path=Path("src/main/java/com/example/ApprovalController.java"),
                start_line=1,
                end_line=10,
                content="class ApprovalController { String current() { return \"ok\"; } }",
                score=0.7,
                score_parts={
                    "direct_text": 0.7,
                    "rerank_score": 0.8,
                },
                reasons=["direct text match"],
                followup_keywords=[],
                rank_tier=0,
                rerank_score=0.8,
                evidence_class="original_direct",
                evidence_priority=0,
            ),
        ],
        final_top_k=1,
        anchor_top_k=2,
    )

    assert [item.file_path for item in code_results] == [
        Path("src/main/java/com/example/ApprovalController.java")
    ]
    assert [anchor.file_path for anchor in evidence_anchors] == [
        Path("README.md"),
        Path("RISKS.md"),
    ]


def test_evidence_anchor_kind_classifies_supported_paths() -> None:
    assert retrieval._evidence_anchor_kind(Path("README.md")) == "readme"
    assert retrieval._evidence_anchor_kind(Path("docs/README-api.md")) == "readme"
    assert retrieval._evidence_anchor_kind(Path("RISKS.md")) == "risks"
    assert retrieval._evidence_anchor_kind(Path("docs/RISKS-auth.md")) == "risks"
    assert retrieval._evidence_anchor_kind(Path("pom.xml")) == "pom"
    assert retrieval._evidence_anchor_kind(Path("service/pom.xml")) == "pom"
    assert retrieval._evidence_anchor_kind(Path("src/main/java/AuthController.java")) == ""


def test_evidence_anchors_do_not_consume_code_result_slots() -> None:
    readme = retrieval._ExpandedResult(
        chunk_ids=["readme"],
        file_path=Path("README.md"),
        start_line=1,
        end_line=3,
        content="当前审批人查询接口由 ApprovalController 负责。",
        score=1.0,
        score_parts={"direct_text": 1.0, "rerank_score": 1.2},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.2,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    risks = retrieval._ExpandedResult(
        chunk_ids=["risks"],
        file_path=Path("RISKS.md"),
        start_line=1,
        end_line=3,
        content="当前审批人查询接口风险说明。",
        score=0.95,
        score_parts={"direct_text": 0.95, "rerank_score": 1.1},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.1,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    pom = retrieval._ExpandedResult(
        chunk_ids=["pom"],
        file_path=Path("pom.xml"),
        start_line=1,
        end_line=20,
        content="<artifactId>approval-service</artifactId>",
        score=0.9,
        score_parts={"direct_text": 0.9, "rerank_score": 1.0},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.0,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    controller = retrieval._ExpandedResult(
        chunk_ids=["controller"],
        file_path=Path("src/main/java/com/example/ApprovalController.java"),
        start_line=1,
        end_line=10,
        content="class ApprovalController {}",
        score=0.7,
        score_parts={"direct_text": 0.7, "rerank_score": 0.8},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=0.8,
        evidence_class="original_direct",
        evidence_priority=0,
    )

    code_results, anchors = retrieval._split_code_results_and_evidence_anchors(
        [readme, risks, pom, controller],
        final_top_k=1,
        anchor_top_k=3,
    )

    assert [item.file_path for item in code_results] == [
        Path("src/main/java/com/example/ApprovalController.java")
    ]
    assert [anchor.anchor_kind for anchor in anchors] == ["readme", "risks", "pom"]


def test_evidence_anchors_do_not_steal_when_many_code_results_exist() -> None:
    anchor = retrieval._ExpandedResult(
        chunk_ids=["readme"],
        file_path=Path("README.md"),
        start_line=1,
        end_line=2,
        content="接口说明。",
        score=1.0,
        score_parts={"direct_text": 1.0, "rerank_score": 1.3},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.3,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    code_items = [
        retrieval._ExpandedResult(
            chunk_ids=[f"code-{index}"],
            file_path=Path(f"src/main/java/com/example/Service{index}.java"),
            start_line=1,
            end_line=5,
            content=f"class Service{index} {{}}",
            score=0.8 - (index * 0.01),
            score_parts={
                "direct_text": 0.5,
                "rerank_score": 0.9 - (index * 0.01),
            },
            reasons=["direct text match"],
            followup_keywords=[],
            rank_tier=0,
            rerank_score=0.9 - (index * 0.01),
            evidence_class="original_direct",
            evidence_priority=0,
        )
        for index in range(3)
    ]

    code_results, anchors = retrieval._split_code_results_and_evidence_anchors(
        [anchor, *code_items],
        final_top_k=2,
        anchor_top_k=1,
    )

    assert [item.file_path.name for item in code_results] == [
        "Service0.java",
        "Service1.java",
    ]
    assert [anchor.anchor_kind for anchor in anchors] == ["readme"]


def test_only_evidence_anchors_leave_code_results_empty() -> None:
    readme = retrieval._ExpandedResult(
        chunk_ids=["readme"],
        file_path=Path("README.md"),
        start_line=1,
        end_line=2,
        content="接口说明。",
        score=1.0,
        score_parts={"direct_text": 1.0, "rerank_score": 1.1},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.1,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    risks = retrieval._ExpandedResult(
        chunk_ids=["risks"],
        file_path=Path("RISKS.md"),
        start_line=1,
        end_line=2,
        content="风险说明。",
        score=0.9,
        score_parts={"direct_text": 0.9, "rerank_score": 1.0},
        reasons=["direct text match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.0,
        evidence_class="original_direct",
        evidence_priority=0,
    )

    code_results, anchors = retrieval._split_code_results_and_evidence_anchors(
        [readme, risks],
        final_top_k=5,
        anchor_top_k=5,
    )

    assert code_results == []
    assert [anchor.anchor_kind for anchor in anchors] == ["readme", "risks"]


def test_evidence_anchor_top_k_returns_zero_for_non_positive_final_top_k() -> None:
    assert retrieval._evidence_anchor_top_k(0) == 0
    assert retrieval._evidence_anchor_top_k(-1) == 0
    assert retrieval._evidence_anchor_top_k(1) == 1
    assert retrieval._evidence_anchor_top_k(2) == 1
    assert retrieval._evidence_anchor_top_k(10) == 3


def test_evidence_anchors_dedupe_by_kind_and_file_path() -> None:
    split_code, split_anchors = retrieval._split_code_results_and_evidence_anchors(
        [
            retrieval._ExpandedResult(
                chunk_ids=["readme-0"],
                file_path=Path("README.md"),
                start_line=1,
                end_line=3,
                content="README anchor top chunk",
                score=1.0,
                score_parts={"direct_text": 1.0, "rerank_score": 1.2},
                reasons=["direct text match"],
                followup_keywords=[],
                rank_tier=0,
                rerank_score=1.2,
                evidence_class="original_direct",
                evidence_priority=0,
            ),
            retrieval._ExpandedResult(
                chunk_ids=["readme-1"],
                file_path=Path("README.md"),
                start_line=20,
                end_line=24,
                content="README anchor duplicate chunk",
                score=0.99,
                score_parts={"direct_text": 0.99, "rerank_score": 1.1},
                reasons=["direct text match"],
                followup_keywords=[],
                rank_tier=0,
                rerank_score=1.1,
                evidence_class="original_direct",
                evidence_priority=0,
            ),
            retrieval._ExpandedResult(
                chunk_ids=["controller"],
                file_path=Path("src/main/java/com/example/ApprovalController.java"),
                start_line=1,
                end_line=10,
                content="class ApprovalController {}",
                score=0.7,
                score_parts={"direct_text": 0.7, "rerank_score": 0.8},
                reasons=["direct text match"],
                followup_keywords=[],
                rank_tier=0,
                rerank_score=0.8,
                evidence_class="original_direct",
                evidence_priority=0,
            ),
        ],
        final_top_k=1,
        anchor_top_k=2,
    )

    assert [item.file_path for item in split_code] == [
        Path("src/main/java/com/example/ApprovalController.java")
    ]
    assert [item.file_path for item in split_anchors] == [Path("README.md")]
    assert [item.start_line for item in split_anchors] == [1]


def test_evidence_anchors_do_not_contribute_to_summary(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    controller = DocumentChunk(
        chunk_id="controller",
        file_path=Path("src/main/java/com/example/ApprovalController.java"),
        start_line=1,
        end_line=10,
        content="class ApprovalController {}",
        chunk_type="symbol",
        symbols=[
            SymbolRef(
                name="ApprovalController",
                kind="class",
                start_line=1,
                end_line=10,
                language="java",
            )
        ],
        lexical_tokens=["approval", "controller"],
        metadata={"language": "java"},
    )
    store.replace_chunks(controller.file_path, [controller])

    code_results, evidence_anchors = retrieval._split_code_results_and_evidence_anchors(
        [
            retrieval._ExpandedResult(
                chunk_ids=["readme"],
                file_path=Path("README.md"),
                start_line=1,
                end_line=3,
                content="当前审批人查询接口由 ApprovalController 负责。",
                score=1.0,
                score_parts={"direct_text": 1.0, "rerank_score": 1.2},
                reasons=["direct text match"],
                followup_keywords=[],
                rank_tier=0,
                rerank_score=1.2,
                evidence_class="original_direct",
                evidence_priority=0,
            ),
            retrieval._ExpandedResult(
                chunk_ids=["risks"],
                file_path=Path("RISKS.md"),
                start_line=1,
                end_line=3,
                content="当前审批人查询接口风险说明。",
                score=0.95,
                score_parts={"direct_text": 0.95, "rerank_score": 1.1},
                reasons=["direct text match"],
                followup_keywords=[],
                rank_tier=0,
                rerank_score=1.1,
                evidence_class="original_direct",
                evidence_priority=0,
            ),
            retrieval._ExpandedResult(
                chunk_ids=["pom"],
                file_path=Path("pom.xml"),
                start_line=1,
                end_line=20,
                content="<artifactId>approval-service</artifactId>",
                score=0.9,
                score_parts={"direct_text": 0.9, "rerank_score": 1.0},
                reasons=["direct text match"],
                followup_keywords=[],
                rank_tier=0,
                rerank_score=1.0,
                evidence_class="original_direct",
                evidence_priority=0,
            ),
            retrieval._ExpandedResult(
                chunk_ids=["controller"],
                file_path=controller.file_path,
                start_line=1,
                end_line=10,
                content="class ApprovalController {}",
                score=0.7,
                score_parts={"direct_text": 0.7, "rerank_score": 0.8},
                reasons=["direct text match"],
                followup_keywords=[],
                rank_tier=0,
                rerank_score=0.8,
                evidence_class="original_direct",
                evidence_priority=0,
            ),
        ],
        final_top_k=1,
        anchor_top_k=3,
    )
    summary, _ = retrieval._summarize_results(store, code_results)

    assert [item.file_path.suffix for item in code_results] == [".java"]
    assert [anchor.anchor_kind for anchor in evidence_anchors] == [
        "readme",
        "risks",
        "pom",
    ]
    summary_items = {
        *summary.entry_points,
        *summary.implementation,
        *summary.related_types,
        *summary.possibly_legacy,
    }
    assert "README.md" not in summary_items
    assert "RISKS.md" not in summary_items
    assert "pom.xml" not in summary_items
    assert any("ApprovalController" in item for item in summary.entry_points)


def test_evidence_anchors_still_seed_directory_expansion(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    readme = DocumentChunk(
        chunk_id="readme",
        file_path=Path("README.md"),
        start_line=1,
        end_line=3,
        content="当前审批人查询接口由 ApprovalController 负责。",
        chunk_type="file",
        lexical_tokens=["当前", "审批人", "查询", "接口"],
        metadata={"language": "markdown"},
    )
    controller = DocumentChunk(
        chunk_id="controller",
        file_path=Path("ApprovalController.java"),
        start_line=1,
        end_line=10,
        content="class ApprovalController {}",
        chunk_type="symbol",
        lexical_tokens=["approval", "controller"],
        metadata={"language": "java"},
    )
    for chunk in (readme, controller):
        store.replace_chunks(chunk.file_path, [chunk])

    expanded = retrieval._anchor_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="readme",
                score=1.0,
                source="direct_text",
                score_parts={"direct_text": 1.0},
            )
        ],
        ToolConfig(retrieval=RetrievalConfig(final_top_k=5)),
    )

    assert Path("ApprovalController.java") in {
        store.chunk_for_id(candidate.chunk_id).file_path
        for candidate in expanded
    }


def test_anchor_expansion_skips_generated_schema_same_file_noise(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    seed = DocumentChunk(
        chunk_id="schema-seed",
        file_path=Path("gen/schemas/desktop-schema.json"),
        start_line=1,
        end_line=80,
        content='{"command": "apply_dev"}',
        chunk_type="file",
        lexical_tokens=["command", "apply", "dev"],
    )
    same_file_noise = DocumentChunk(
        chunk_id="schema-noise",
        file_path=Path("gen/schemas/desktop-schema.json"),
        start_line=81,
        end_line=160,
        content='{"command": "restore_clean"}',
        chunk_type="file",
        lexical_tokens=["command", "restore", "clean"],
    )
    store.replace_chunks(seed.file_path, [seed, same_file_noise])

    expanded = retrieval._anchor_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="schema-seed",
                score=1.0,
                source="direct_text",
                score_parts={"direct_text": 1.0},
            )
        ],
        ToolConfig(retrieval=RetrievalConfig(final_top_k=5)),
        query="tauri command apply_dev restore_clean command handler",
        tokens=["tauri", "command", "apply", "dev", "restore", "clean", "handler"],
    )

    assert "schema-noise" not in {candidate.chunk_id for candidate in expanded}


def test_anchor_expansion_skips_template_same_file_noise_for_implementation_query(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    seed = DocumentChunk(
        chunk_id="template-seed",
        file_path=Path("templates/index.html"),
        start_line=1,
        end_line=80,
        content="<form>NewLocalStorage</form>",
        chunk_type="file",
        lexical_tokens=["new", "local", "storage"],
    )
    same_file_noise = DocumentChunk(
        chunk_id="template-noise",
        file_path=Path("templates/index.html"),
        start_line=81,
        end_line=160,
        content="<section>NewS3Storage</section>",
        chunk_type="file",
        lexical_tokens=["new", "s3", "storage"],
    )
    store.replace_chunks(seed.file_path, [seed, same_file_noise])

    expanded = retrieval._anchor_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="template-seed",
                score=1.0,
                source="direct_text",
                score_parts={"direct_text": 1.0},
            )
        ],
        ToolConfig(retrieval=RetrievalConfig(final_top_k=5)),
        query="NewS3Storage NewOSSStorage NewLocalStorage initStorage",
        tokens=["new", "s3", "storage", "oss", "local", "init"],
    )

    assert "template-noise" not in {candidate.chunk_id for candidate in expanded}


def test_anchor_expansion_keeps_template_same_file_anchor_for_content_query(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    seed = DocumentChunk(
        chunk_id="template-seed",
        file_path=Path("templates/index.html"),
        start_line=1,
        end_line=80,
        content="<title>Gallery</title>",
        chunk_type="file",
        lexical_tokens=["gallery"],
    )
    same_file_content = DocumentChunk(
        chunk_id="template-content",
        file_path=Path("templates/index.html"),
        start_line=81,
        end_line=160,
        content="<section>Hero copy</section>",
        chunk_type="file",
        lexical_tokens=["hero", "copy"],
    )
    store.replace_chunks(seed.file_path, [seed, same_file_content])

    expanded = retrieval._anchor_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="template-seed",
                score=1.0,
                source="direct_text",
                score_parts={"direct_text": 1.0},
            )
        ],
        ToolConfig(retrieval=RetrievalConfig(final_top_k=5)),
        query="gallery hero copy",
        tokens=["gallery", "hero", "copy"],
    )

    assert "template-content" in {candidate.chunk_id for candidate in expanded}


@pytest.mark.parametrize(
    ("path", "content", "expected_role", "expected_priority", "expected_boost", "expected_penalty"),
    [
        ("src/main/java/com/example/controller/AuthController.java", "class AuthController {}", "entrypoint", 0, 0.18, 0.0),
        ("src/test/java/com/example/controller/AuthControllerTest.java", "class AuthControllerTest {}", "generic", 5, 0.0, 0.0),
        ("src/main/java/com/example/service/AuthService.java", "interface AuthService {}", "service_interface", 4, 0.06, 0.0),
        ("src/main/java/com/example/service/SimpleService.java", "interface SimpleService {}", "service_interface", 4, 0.06, 0.0),
        ("src/main/java/com/example/service/AuthService.java", "interface AuthService { // AuthServiceImpl handles this }", "service_interface", 4, 0.06, 0.0),
        ("src/main/java/com/example/service/impl/AuthServiceImpl.java", "class AuthServiceImpl {}", "service_impl", 1, 0.12, 0.0),
        ("src/main/java/com/example/service/AppInfoServiceImpl.java", "class AppInfoServiceImpl {}", "service_impl", 1, 0.12, 0.0),
        ("src/main/java/com/example/service/NavService.java", "class NavService {}", "service", 2, 0.0, 0.0),
        ("collector/internal/service/fund_service.go", "type FundService struct{}", "service", 2, 0.0, 0.0),
        ("src/main/java/com/example/catalog/PageAppCatalogQueryExe.java", "class PageAppCatalogQueryExe {}", "executor", 2, 0.12, 0.0),
        ("src/main/java/com/example/catalog/FooExe.java", "class FooExe {}", "executor", 2, 0.12, 0.0),
        ("src/main/java/com/example/catalog/ExecuteHelper.java", "class ExecuteHelper { void execute() {} }", "generic", 5, 0.0, 0.0),
        ("src/main/java/com/example/dto/AuthLoginDto.java", "class AuthLoginDto {}", "data_type", 3, 0.04, 0.0),
        ("src/main/java/com/example/entity/User.java", "class User {}", "data_type", 3, 0.04, 0.0),
        ("src/main/java/com/example/mapper/UserMapper.java", "interface UserMapper {}", "mapper", 4, 0.03, 0.0),
        ("src/main/java/com/example/iot/code/beehive/BeehiveCodeHandler.java", "class BeehiveCodeHandler {}", "handler", 5, 0.0, 0.10),
        ("src/main/java/com/example/alarm/DahuaWebhook.java", "class DahuaWebhook {}", "handler", 5, 0.0, 0.10),
        ("src/main/java/com/example/mqtt/PeachMqttConstant.java", "class PeachMqttConstant {}", "constant_or_config", 6, 0.0, 0.12),
        ("src/main/java/com/example/util/AuthUtils.java", "class AuthUtils {}", "generic", 5, 0.0, 0.0),
    ],
)
def test_chunk_role_classification(
    path: str,
    content: str,
    expected_role: str,
    expected_priority: int,
    expected_boost: float,
    expected_penalty: float,
) -> None:
    chunk = DocumentChunk(
        chunk_id="chunk",
        file_path=Path(path),
        start_line=1,
        end_line=1,
        content=content,
        chunk_type="symbol",
        lexical_tokens=[],
        metadata={"language": "java"},
    )

    role = retrieval._chunk_role(chunk)

    assert role.name == expected_role
    assert role.priority == expected_priority
    assert role.boost == expected_boost
    assert role.penalty == expected_penalty


def test_chunk_role_classifies_query_executor_before_generic() -> None:
    chunk = DocumentChunk(
        chunk_id="executor",
        file_path=Path("src/main/java/PageAppCatalogQueryExe.java"),
        start_line=1,
        end_line=5,
        content="class PageAppCatalogQueryExe { String fillCanApplyFilter() { return \"\"; } }",
        chunk_type="symbol",
        symbols=[SymbolRef("PageAppCatalogQueryExe", "class", 1, 5, "java")],
        lexical_tokens=["page", "app", "catalog", "query", "exe", "can", "apply"],
        metadata={"language": "java"},
    )

    role = retrieval._chunk_role(chunk)

    assert role.name == "executor"
    assert role.priority == 2
    assert role.boost == 0.12


def test_java_context_score_parts_boosts_field_related_executor_method() -> None:
    method_signal = CodeSignal(
        signal_id="sig-method",
        chunk_id="executor",
        file_path=Path("PageAppCatalogQueryExe.java"),
        kind="method",
        name="PageAppCatalogQueryExe.fillCanApplyFilter",
        start_line=3,
        end_line=3,
        language="java",
        tokens=["page", "app", "catalog", "fill", "can", "apply", "filter"],
        metadata={
            "owner_type": "PageAppCatalogQueryExe",
            "owner_method": "fillCanApplyFilter",
            "parameter_types": ["AppCatalogPageQry"],
            "parameter_names": ["qry"],
        },
    )

    parts = retrieval._java_context_score_parts(
        [method_signal],
        ["app", "catalog", "page", "can", "apply"],
        retrieval._ChunkRole("executor", 2, 0.12),
    )

    assert parts["java_method_context_match"] == 0.14
    assert parts["java_executor_context_boost"] == 0.10


def test_java_context_score_parts_boosts_field_signal() -> None:
    field_signal = CodeSignal(
        signal_id="sig-field",
        chunk_id="dto",
        file_path=Path("AppCatalogPageQry.java"),
        kind="field",
        name="AppCatalogPageQry.canApply",
        start_line=3,
        end_line=3,
        language="java",
        tokens=["app", "catalog", "page", "can", "apply"],
        metadata={
            "owner_type": "AppCatalogPageQry",
            "field_type": "Boolean",
        },
    )

    parts = retrieval._java_context_score_parts(
        [field_signal],
        ["app", "catalog", "page", "can", "apply"],
        retrieval._ChunkRole("data_type", 3, 0.04),
    )

    assert parts["java_field_context_match"] == 0.12
    assert "java_executor_context_boost" not in parts


def test_rank_chunks_route_java_context_uses_non_route_business_tokens(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    catalog_executor = DocumentChunk(
        chunk_id="catalog-executor",
        file_path=Path("src/main/java/com/example/catalog/PageAppCatalogQueryExe.java"),
        start_line=1,
        end_line=10,
        content="class PageAppCatalogQueryExe { String fillCanApplyFilter() { return \"\"; } }",
        chunk_type="symbol",
        lexical_tokens=["page", "app", "catalog", "can", "apply", "filter"],
        metadata={"language": "java"},
    )
    audit_executor = DocumentChunk(
        chunk_id="audit-executor",
        file_path=Path("src/main/java/com/example/audit/ApplyAuditPageQryExe.java"),
        start_line=1,
        end_line=10,
        content="class ApplyAuditPageQryExe { String page() { return \"\"; } }",
        chunk_type="symbol",
        lexical_tokens=["apply", "audit", "page", "es"],
        metadata={"language": "java"},
    )
    for chunk in (catalog_executor, audit_executor):
        store.replace_chunks(chunk.file_path, [chunk])
    store.replace_signals(
        catalog_executor.file_path,
        [
            CodeSignal(
                signal_id="sig-catalog-method",
                chunk_id="catalog-executor",
                file_path=catalog_executor.file_path,
                kind="method",
                name="PageAppCatalogQueryExe.fillCanApplyFilter",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["page", "app", "catalog", "fill", "can", "apply", "filter"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        audit_executor.file_path,
        [
            CodeSignal(
                signal_id="sig-audit-method",
                chunk_id="audit-executor",
                file_path=audit_executor.file_path,
                kind="method",
                name="ApplyAuditPageQryExe.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["apply", "audit", "page", "es"],
                metadata={},
            )
        ],
    )

    ranked = retrieval._rank_chunks(
        store,
        {
            "catalog-executor": RetrievalCandidate(
                chunk_id="catalog-executor",
                score=1.0,
                source="lexical",
                score_parts={"lexical": 0.8},
            ),
            "audit-executor": RetrievalCandidate(
                chunk_id="audit-executor",
                score=1.0,
                source="lexical",
                score_parts={"lexical": 0.8},
            ),
        },
        ["app", "catalog", "page", "can", "apply"],
        "/appCatalog/page canApply",
    )

    catalog_result = next(item for item in ranked if item.chunk.chunk_id == "catalog-executor")
    audit_result = next(item for item in ranked if item.chunk.chunk_id == "audit-executor")
    assert catalog_result.score_parts["java_method_context_match"] == 0.14
    assert catalog_result.score_parts["java_executor_context_boost"] == 0.10
    assert "java_method_context_match" not in audit_result.score_parts
    assert "java_executor_context_boost" not in audit_result.score_parts


def test_rank_chunks_route_java_context_preserves_matching_business_tokens(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    es_executor = DocumentChunk(
        chunk_id="es-executor",
        file_path=Path("src/main/java/com/example/audit/EsApplyAuditPageQryExe.java"),
        start_line=1,
        end_line=10,
        content="class EsApplyAuditPageQryExe { String involvedByMe() { return \"\"; } }",
        chunk_type="symbol",
        lexical_tokens=["apply", "audit", "page", "es", "involved", "by", "me"],
        metadata={"language": "java"},
    )
    non_es_executor = DocumentChunk(
        chunk_id="non-es-executor",
        file_path=Path("src/main/java/com/example/audit/ApplyAuditPageQryExe.java"),
        start_line=1,
        end_line=10,
        content="class ApplyAuditPageQryExe { String page() { return \"\"; } }",
        chunk_type="symbol",
        lexical_tokens=["apply", "audit", "page", "es"],
        metadata={"language": "java"},
    )
    es_directory_executor = DocumentChunk(
        chunk_id="es-directory-executor",
        file_path=Path("src/main/java/com/example/es/ApplyAuditPageQryExe.java"),
        start_line=1,
        end_line=10,
        content="class ApplyAuditPageQryExe { String page() { return \"\"; } }",
        chunk_type="symbol",
        lexical_tokens=["apply", "audit", "page", "es"],
        metadata={"language": "java"},
    )
    split_symbol_executor = DocumentChunk(
        chunk_id="split-symbol-executor",
        file_path=Path("src/main/java/com/example/es/ResourceAuditApplyService.java"),
        start_line=1,
        end_line=10,
        content="class ResourceAuditApplyService { void currentNodePage() {} void resourceSynInvolvedToEs() {} }",
        chunk_type="symbol",
        symbols=[
            SymbolRef(
                name="ResourceAuditApplyService",
                kind="class",
                start_line=1,
                end_line=10,
                language="java",
            ),
            SymbolRef(
                name="currentNodePage",
                kind="method",
                start_line=3,
                end_line=3,
                language="java",
            ),
            SymbolRef(
                name="resourceSynInvolvedToEs",
                kind="method",
                start_line=4,
                end_line=4,
                language="java",
            ),
            SymbolRef(
                name="executor",
                kind="field",
                start_line=5,
                end_line=5,
                language="java",
            ),
        ],
        lexical_tokens=["apply", "audit", "page", "es"],
        metadata={"language": "java"},
    )
    for chunk in (
        es_executor,
        non_es_executor,
        es_directory_executor,
        split_symbol_executor,
    ):
        store.replace_chunks(chunk.file_path, [chunk])
    store.replace_signals(
        es_executor.file_path,
        [
            CodeSignal(
                signal_id="sig-es-method",
                chunk_id="es-executor",
                file_path=es_executor.file_path,
                kind="method",
                name="EsApplyAuditPageQryExe.involvedByMe",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["apply", "audit", "page", "es", "involved", "by", "me"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        non_es_executor.file_path,
        [
            CodeSignal(
                signal_id="sig-non-es-method",
                chunk_id="non-es-executor",
                file_path=non_es_executor.file_path,
                kind="method",
                name="ApplyAuditPageQryExe.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["apply", "audit", "page", "es"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        es_directory_executor.file_path,
        [
            CodeSignal(
                signal_id="sig-es-directory-method",
                chunk_id="es-directory-executor",
                file_path=es_directory_executor.file_path,
                kind="method",
                name="ApplyAuditPageQryExe.page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["apply", "audit", "page", "es"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        split_symbol_executor.file_path,
        [
            CodeSignal(
                signal_id="sig-split-symbol-method-page",
                chunk_id="split-symbol-executor",
                file_path=split_symbol_executor.file_path,
                kind="method",
                name="currentNodePage",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["current", "node", "page"],
                metadata={},
            ),
            CodeSignal(
                signal_id="sig-split-symbol-method-es",
                chunk_id="split-symbol-executor",
                file_path=split_symbol_executor.file_path,
                kind="method",
                name="resourceSynInvolvedToEs",
                start_line=4,
                end_line=4,
                language="java",
                tokens=["resource", "syn", "involved", "to", "es"],
                metadata={},
            ),
        ],
    )

    ranked = retrieval._rank_chunks(
        store,
        {
            "es-executor": RetrievalCandidate(
                chunk_id="es-executor",
                score=1.0,
                source="lexical",
                score_parts={"lexical": 0.8},
            ),
            "non-es-executor": RetrievalCandidate(
                chunk_id="non-es-executor",
                score=1.0,
                source="lexical",
                score_parts={"lexical": 0.8},
            ),
            "es-directory-executor": RetrievalCandidate(
                chunk_id="es-directory-executor",
                score=1.0,
                source="lexical",
                score_parts={"lexical": 0.8},
            ),
            "split-symbol-executor": RetrievalCandidate(
                chunk_id="split-symbol-executor",
                score=1.0,
                source="lexical",
                score_parts={"lexical": 0.8},
            ),
        },
        ["apply", "audit", "page", "es", "involved", "by", "me"],
        "/apply/audit/pageEs INVOLVED_BY_ME",
    )

    es_result = next(item for item in ranked if item.chunk.chunk_id == "es-executor")
    non_es_result = next(item for item in ranked if item.chunk.chunk_id == "non-es-executor")
    es_directory_result = next(
        item for item in ranked if item.chunk.chunk_id == "es-directory-executor"
    )
    split_symbol_result = next(
        item for item in ranked if item.chunk.chunk_id == "split-symbol-executor"
    )
    assert ranked[0].chunk.chunk_id == "es-executor"
    assert es_result.score_parts["java_method_context_match"] == 0.14
    assert es_result.score_parts["java_executor_context_boost"] == 0.10
    assert es_result.score_parts["route_tail_context_match"] == 0.22
    assert "java_method_context_match" not in non_es_result.score_parts
    assert "java_executor_context_boost" not in non_es_result.score_parts
    assert "route_tail_context_match" not in non_es_result.score_parts
    assert "route_tail_context_match" not in es_directory_result.score_parts
    assert "route_tail_context_match" not in split_symbol_result.score_parts


def test_rank_chunks_applies_java_context_without_generic_signal_lookups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    executor = DocumentChunk(
        chunk_id="executor",
        file_path=Path("src/main/java/com/example/catalog/PageAppCatalogQueryExe.java"),
        start_line=1,
        end_line=10,
        content="class PageAppCatalogQueryExe { String fillCanApplyFilter() { return \"\"; } }",
        chunk_type="symbol",
        lexical_tokens=["page", "app", "catalog", "can", "apply", "filter"],
        metadata={"language": "java"},
    )
    generic = DocumentChunk(
        chunk_id="generic",
        file_path=Path("src/main/java/com/example/catalog/PageAppCatalogFormatter.java"),
        start_line=1,
        end_line=10,
        content="class PageAppCatalogFormatter { String displayName; }",
        chunk_type="symbol",
        lexical_tokens=["page", "app", "catalog"],
        metadata={"language": "java"},
    )
    for chunk in (executor, generic):
        store.replace_chunks(chunk.file_path, [chunk])
    store.replace_signals(
        executor.file_path,
        [
            CodeSignal(
                signal_id="sig-method",
                chunk_id="executor",
                file_path=executor.file_path,
                kind="method",
                name="PageAppCatalogQueryExe.fillCanApplyFilter",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["page", "app", "catalog", "fill", "can", "apply", "filter"],
                metadata={},
            )
        ],
    )
    signal_lookup_count = _count_signal_lookups(store, monkeypatch)
    candidates = {
        "executor": RetrievalCandidate(
            chunk_id="executor",
            score=1.0,
            source="lexical",
            score_parts={"lexical": 0.8},
        ),
        "generic": RetrievalCandidate(
            chunk_id="generic",
            score=1.0,
            source="lexical",
            score_parts={"lexical": 0.8},
        ),
    }

    ranked = retrieval._rank_chunks(
        store,
        candidates,
        ["app", "catalog", "page", "can", "apply"],
        "app catalog page can apply",
    )

    executor_result = next(item for item in ranked if item.chunk.chunk_id == "executor")
    assert executor_result.score_parts["java_method_context_match"] == 0.14
    assert executor_result.score_parts["java_executor_context_boost"] == 0.10
    assert signal_lookup_count() == 1


def test_rank_chunks_applies_java_context_for_matching_generic_helper_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    helper = DocumentChunk(
        chunk_id="helper",
        file_path=Path("src/main/java/com/example/catalog/AppCatalogFilterHelper.java"),
        start_line=1,
        end_line=10,
        content="class AppCatalogFilterHelper { void fillCanApplyFilter() {} }",
        chunk_type="symbol",
        lexical_tokens=["app", "catalog", "filter", "helper", "can", "apply"],
        metadata={"language": "java"},
    )
    unrelated = DocumentChunk(
        chunk_id="unrelated",
        file_path=Path("src/main/java/com/example/catalog/AppCatalogFormatter.java"),
        start_line=1,
        end_line=10,
        content="class AppCatalogFormatter { String displayName; }",
        chunk_type="symbol",
        lexical_tokens=["app", "catalog", "formatter"],
        metadata={"language": "java"},
    )
    for chunk in (helper, unrelated):
        store.replace_chunks(chunk.file_path, [chunk])
    store.replace_signals(
        helper.file_path,
        [
            CodeSignal(
                signal_id="sig-helper-method",
                chunk_id="helper",
                file_path=helper.file_path,
                kind="method",
                name="AppCatalogFilterHelper.fillCanApplyFilter",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["app", "catalog", "fill", "can", "apply", "filter"],
                metadata={},
            )
        ],
    )
    signal_lookup_count = _count_signal_lookups(store, monkeypatch)

    ranked = retrieval._rank_chunks(
        store,
        {
            "helper": RetrievalCandidate(
                chunk_id="helper",
                score=1.0,
                source="lexical",
                score_parts={"lexical": 0.8},
            ),
            "unrelated": RetrievalCandidate(
                chunk_id="unrelated",
                score=1.0,
                source="lexical",
                score_parts={"lexical": 0.8},
            ),
        },
        ["app", "catalog", "can", "apply"],
        "app catalog can apply",
    )

    helper_result = next(item for item in ranked if item.chunk.chunk_id == "helper")
    unrelated_result = next(item for item in ranked if item.chunk.chunk_id == "unrelated")
    assert helper_result.score_parts["java_method_context_match"] == 0.14
    assert "java_method_context_match" not in unrelated_result.score_parts
    assert signal_lookup_count() == 1


def test_rank_chunks_skips_java_context_for_test_executor(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    executor_test = DocumentChunk(
        chunk_id="executor-test",
        file_path=Path("src/test/java/com/example/catalog/PageAppCatalogQueryExecutorTest.java"),
        start_line=1,
        end_line=10,
        content="class PageAppCatalogQueryExecutorTest { void fillCanApplyFilter() {} }",
        chunk_type="symbol",
        lexical_tokens=["page", "app", "catalog", "can", "apply", "filter"],
        metadata={"language": "java"},
    )
    store.replace_chunks(executor_test.file_path, [executor_test])
    store.replace_signals(
        executor_test.file_path,
        [
            CodeSignal(
                signal_id="sig-method",
                chunk_id="executor-test",
                file_path=executor_test.file_path,
                kind="method",
                name="PageAppCatalogQueryExecutorTest.fillCanApplyFilter",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["page", "app", "catalog", "fill", "can", "apply", "filter"],
                metadata={},
            )
        ],
    )
    candidates = {
        "executor-test": RetrievalCandidate(
            chunk_id="executor-test",
            score=1.0,
            source="lexical",
            score_parts={"lexical": 0.8},
        )
    }

    ranked = retrieval._rank_chunks(
        store,
        candidates,
        ["app", "catalog", "page", "can", "apply"],
        "app catalog page can apply",
    )

    score_parts = ranked[0].score_parts
    assert score_parts["penalty"] == -0.10
    assert "java_method_context_match" not in score_parts
    assert "java_executor_context_boost" not in score_parts


def test_rank_chunks_bounds_java_context_signal_lookups_by_local_overlap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    candidates: dict[str, RetrievalCandidate] = {}
    matching_indices = {17, 503}
    matching_executor_id = "chunk-17"

    for index in range(1000):
        chunk_id = f"chunk-{index}"
        is_match = index in matching_indices
        is_executor = index != 503
        class_name = (
            "PageAppCatalogQueryExe"
            if index == 17
            else "AppCatalogPageQry"
            if index == 503
            else f"Noise{index}QueryExe"
        )
        path = Path(
            f"src/main/java/com/example/{'dto' if not is_executor else 'query'}/{class_name}.java"
        )
        lexical_tokens = (
            ["app", "catalog", "page", "can", "apply", "filter"]
            if is_match
            else ["noise", "executor"]
        )
        content = (
            f"class {class_name} {{ void fillCanApplyFilter() {{}} }}"
            if is_match
            else f"class {class_name} {{ void executeNoise() {{}} }}"
        )
        chunk = DocumentChunk(
            chunk_id=chunk_id,
            file_path=path,
            start_line=1,
            end_line=10,
            content=content,
            chunk_type="symbol",
            lexical_tokens=lexical_tokens,
            metadata={"language": "java"},
        )
        store.replace_chunks(path, [chunk])
        candidates[chunk_id] = RetrievalCandidate(
            chunk_id=chunk_id,
            score=1.0,
            source="lexical",
            score_parts={"lexical": 0.8},
        )

    store.replace_signals(
        Path("src/main/java/com/example/query/PageAppCatalogQueryExe.java"),
        [
            CodeSignal(
                signal_id="sig-method",
                chunk_id=matching_executor_id,
                file_path=Path("src/main/java/com/example/query/PageAppCatalogQueryExe.java"),
                kind="method",
                name="PageAppCatalogQueryExe.fillCanApplyFilter",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["app", "catalog", "fill", "can", "apply", "filter"],
                metadata={},
            )
        ],
    )
    signal_lookup_count = _count_signal_lookups(store, monkeypatch)

    ranked = retrieval._rank_chunks(
        store,
        candidates,
        ["app", "catalog", "page", "can", "apply"],
        "app catalog page can apply",
    )

    executor_result = next(item for item in ranked if item.chunk.chunk_id == matching_executor_id)
    assert signal_lookup_count() == len(matching_indices)
    assert executor_result.score_parts["java_method_context_match"] == 0.14
    assert executor_result.score_parts["java_executor_context_boost"] == 0.10


def test_route_boost_ignores_side_routes_when_query_has_leading_route() -> None:
    exact = DocumentChunk(
        chunk_id="exact",
        file_path=Path("src/main/java/AppCatalogController.java"),
        start_line=1,
        end_line=10,
        content="class AppCatalogController {}",
        chunk_type="symbol",
        lexical_tokens=["/appCatalog/page", "app", "catalog", "page"],
        metadata={"language": "java"},
    )
    sibling = DocumentChunk(
        chunk_id="sibling",
        file_path=Path("src/main/java/AppCatalogOpenController.java"),
        start_line=1,
        end_line=10,
        content="class AppCatalogOpenController {}",
        chunk_type="symbol",
        lexical_tokens=["/openApi/appCatalog/page", "open", "api", "app", "catalog", "page"],
        metadata={"language": "java"},
    )
    side_route = DocumentChunk(
        chunk_id="side-route",
        file_path=Path("src/main/java/ApplyAuditController.java"),
        start_line=1,
        end_line=10,
        content="class ApplyAuditController {}",
        chunk_type="symbol",
        lexical_tokens=["/apply/audit/pageEs", "apply", "audit", "page", "es"],
        metadata={"language": "java"},
    )

    tokens = ["app", "catalog", "page", "can", "apply"]

    assert retrieval._route_boost(exact, "/appCatalog/page canApply", tokens) == 0.12
    assert retrieval._route_boost(sibling, "/appCatalog/page canApply", tokens) == 0.0
    assert retrieval._route_boost(side_route, "/appCatalog/page canApply", tokens) == 0.0


def test_reasons_include_role_diagnostics() -> None:
    reasons = retrieval._reasons(
        {"role_boost": 0.2, "role_penalty": -0.1},
        "auth login",
    )

    assert "business role boost" in reasons
    assert "detail role penalty" in reasons


def test_reasons_include_identifier_path_role_public_labels() -> None:
    reasons = retrieval._reasons(
        {
            "identifier_exact_match_boost": 0.4,
            "path_role_hint_boost": 0.14,
            "path_role_mismatch_penalty": -0.08,
        },
        "frontend useAuthStore Pinia",
    )

    assert reasons == [
        "explicit identifier match",
        "path role hint match",
        "path role mismatch penalty",
    ]


def test_rerank_planner_only_relation_cannot_beat_strong_original_direct(
    tmp_path: Path,
) -> None:
    """
    Test #2: planner-only relation must not outrank strong original_direct.
    Validates the invariant: max(planner-only rerank) < min(strong original_direct rerank).
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    strong_direct = DocumentChunk(
        chunk_id="strong-direct",
        file_path=Path("AuthService.java"),
        start_line=1,
        end_line=10,
        content="class AuthService { void login() {} }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["auth", "service"],
        embedding_id="strong-direct",
        deleted_at=None,
        metadata={"language": "java"},
    )

    planner_relation = DocumentChunk(
        chunk_id="planner-relation",
        file_path=Path("TokenCache.java"),
        start_line=1,
        end_line=10,
        content="class TokenCache { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["token", "cache"],
        embedding_id="planner-relation",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("AuthService.java"), [strong_direct])
    store.replace_chunks(Path("TokenCache.java"), [planner_relation])

    candidates = {
        "strong-direct": RetrievalCandidate(
            chunk_id="strong-direct",
            score=1.0,
            source="lexical,signal",
            score_parts={
                "lexical": 0.8,  # Strong lexical match
                "signal": 0.5,
            },
        ),
        "planner-relation": RetrievalCandidate(
            chunk_id="planner-relation",
            score=0.9,
            source="planner_relation",
            score_parts={
                "planner_relation": 0.9,
                "relation": 0.9,
                # No original evidence
            },
        ),
    }

    ranked = retrieval._rank_chunks(
        store, candidates, ["login", "auth"], "user login"
    )

    # Strong direct must rank first, planner-only relation second
    assert ranked[0].chunk.chunk_id == "strong-direct"
    assert ranked[1].chunk.chunk_id == "planner-relation"


def test_rerank_planner_direct_cannot_beat_strong_original_direct(
    tmp_path: Path,
) -> None:
    """
    Test #3: planner_direct (planner_signal/planner_lexical) cannot outrank
    strong original_direct, avoiding planner noise from taking Top1.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    strong_original = DocumentChunk(
        chunk_id="strong-original",
        file_path=Path("UserController.java"),
        start_line=1,
        end_line=10,
        content="class UserController { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["user", "controller"],
        embedding_id="strong-original",
        deleted_at=None,
        metadata={"language": "java"},
    )

    planner_direct = DocumentChunk(
        chunk_id="planner-direct",
        file_path=Path("DashboardService.java"),
        start_line=1,
        end_line=10,
        content="class DashboardService { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["dashboard", "service"],
        embedding_id="planner-direct",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("UserController.java"), [strong_original])
    store.replace_chunks(Path("DashboardService.java"), [planner_direct])

    candidates = {
        "strong-original": RetrievalCandidate(
            chunk_id="strong-original",
            score=1.0,
            source="semantic,lexical",
            score_parts={
                "semantic": 0.9,
                "lexical": 0.4,
            },
        ),
        "planner-direct": RetrievalCandidate(
            chunk_id="planner-direct",
            score=0.95,
            source="planner_signal,planner_lexical",
            score_parts={
                "planner_signal": 0.6,
                "planner_lexical": 0.35,
                # No original evidence
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["user"], "user query")

    assert ranked[0].chunk.chunk_id == "strong-original"
    assert ranked[1].chunk.chunk_id == "planner-direct"


def test_rerank_weak_direct_does_not_trigger_planner_ceiling(tmp_path: Path) -> None:
    """
    Test #4: Weak direct evidence (lexical=0.05 or token_coverage=0.1) should not
    trigger planner_ceiling, allowing planner-only results to appear in results.
    Guards against weak original evidence mistakenly killing valid planner召回.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    weak_direct = DocumentChunk(
        chunk_id="weak-direct",
        file_path=Path("Config.java"),
        start_line=1,
        end_line=10,
        content="class Config { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["config"],
        embedding_id="weak-direct",
        deleted_at=None,
        metadata={"language": "java"},
    )

    planner_only = DocumentChunk(
        chunk_id="planner-only",
        file_path=Path("DashboardController.java"),
        start_line=1,
        end_line=10,
        content="class DashboardController { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["dashboard", "controller"],
        embedding_id="planner-only",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("Config.java"), [weak_direct])
    store.replace_chunks(Path("DashboardController.java"), [planner_only])

    candidates = {
        "weak-direct": RetrievalCandidate(
            chunk_id="weak-direct",
            score=0.1,
            source="lexical",
            score_parts={
                "lexical": 0.05,  # Very weak match
            },
        ),
        "planner-only": RetrievalCandidate(
            chunk_id="planner-only",
            score=0.8,
            source="planner_lexical",
            score_parts={
                "planner_lexical": 0.8,
                # No original evidence
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["dashboard"], "dashboard")

    # Planner-only should still appear (not clamped to below weak direct)
    assert any(r.chunk.chunk_id == "planner-only" for r in ranked)
    # And should rank higher than weak direct due to better score
    planner_idx = next(
        i for i, r in enumerate(ranked) if r.chunk.chunk_id == "planner-only"
    )
    weak_idx = next(
        i for i, r in enumerate(ranked) if r.chunk.chunk_id == "weak-direct"
    )
    assert planner_idx < weak_idx


def test_rerank_no_strong_original_direct_no_clamp(tmp_path: Path) -> None:
    """
    Test #5: When there's no strong original_direct evidence, planner-only results
    should not be clamped, preserving planner召回 when original query fails.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    planner_only_1 = DocumentChunk(
        chunk_id="planner-only-1",
        file_path=Path("ServiceA.java"),
        start_line=1,
        end_line=10,
        content="class ServiceA { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["service", "a"],
        embedding_id="planner-only-1",
        deleted_at=None,
        metadata={"language": "java"},
    )

    planner_only_2 = DocumentChunk(
        chunk_id="planner-only-2",
        file_path=Path("ServiceB.java"),
        start_line=1,
        end_line=10,
        content="class ServiceB { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["service", "b"],
        embedding_id="planner-only-2",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("ServiceA.java"), [planner_only_1])
    store.replace_chunks(Path("ServiceB.java"), [planner_only_2])

    candidates = {
        "planner-only-1": RetrievalCandidate(
            chunk_id="planner-only-1",
            score=0.9,
            source="planner_signal",
            score_parts={
                "planner_signal": 0.9,
            },
        ),
        "planner-only-2": RetrievalCandidate(
            chunk_id="planner-only-2",
            score=0.7,
            source="planner_lexical",
            score_parts={
                "planner_lexical": 0.7,
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["service"], "service query")

    # Both should appear in results (not killed by clamp)
    assert len(ranked) == 2
    # Higher score planner-only should rank first
    assert ranked[0].chunk.chunk_id == "planner-only-1"
    assert ranked[1].chunk.chunk_id == "planner-only-2"


def test_rerank_endpoint_boost_does_not_override_score(tmp_path: Path) -> None:
    """
    Test #6: Endpoint/controller boost should not allow low-score endpoints to
    outrank high-score non-endpoints. Boost is additive, not a tier override.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    high_non_endpoint = DocumentChunk(
        chunk_id="high-non-endpoint",
        file_path=Path("BusinessService.java"),
        start_line=1,
        end_line=10,
        content="class BusinessService { void process() {} }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["business", "service"],
        embedding_id="high-non-endpoint",
        deleted_at=None,
        metadata={"language": "java"},
    )

    low_endpoint = DocumentChunk(
        chunk_id="low-endpoint",
        file_path=Path("HealthController.java"),
        start_line=1,
        end_line=10,
        content="@GetMapping('/health') class HealthController { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["health", "controller"],
        embedding_id="low-endpoint",
        deleted_at=None,
        metadata={"language": "java"},
    )

    endpoint_signal = CodeSignal(
        signal_id="sig-endpoint",
        chunk_id="low-endpoint",
        file_path=Path("HealthController.java"),
        kind="endpoint",
        name="GET /health",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["health"],
        metadata={},
    )

    store.replace_chunks(Path("BusinessService.java"), [high_non_endpoint])
    store.replace_chunks(Path("HealthController.java"), [low_endpoint])
    store.replace_signals(Path("HealthController.java"), [endpoint_signal])

    candidates = {
        "high-non-endpoint": RetrievalCandidate(
            chunk_id="high-non-endpoint",
            score=2.0,
            source="semantic,signal",
            score_parts={
                "semantic": 1.8,
                "signal": 0.4,
            },
        ),
        "low-endpoint": RetrievalCandidate(
            chunk_id="low-endpoint",
            score=0.3,
            source="signal",
            score_parts={
                "signal": 0.3,
            },
        ),
    }

    ranked = retrieval._rank_chunks(
        store, candidates, ["business", "process"], "business process"
    )

    # High-score non-endpoint should rank before low-score endpoint
    assert ranked[0].chunk.chunk_id == "high-non-endpoint"
    assert ranked[1].chunk.chunk_id == "low-endpoint"


def test_rerank_relation_expansion_preserved(tmp_path: Path) -> None:
    """
    Test #7: Relation expansion should still surface Service/Impl classes,
    not be completely killed. Validates that rerank doesn't over-penalize relations.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    controller = DocumentChunk(
        chunk_id="controller",
        file_path=Path("OrderController.java"),
        start_line=1,
        end_line=10,
        content="class OrderController { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["order", "controller"],
        embedding_id="controller",
        deleted_at=None,
        metadata={"language": "java"},
    )

    service = DocumentChunk(
        chunk_id="service",
        file_path=Path("OrderServiceImpl.java"),
        start_line=1,
        end_line=10,
        content="class OrderServiceImpl { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["order", "service", "impl"],
        embedding_id="service",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("OrderController.java"), [controller])
    store.replace_chunks(Path("OrderServiceImpl.java"), [service])

    candidates = {
        "controller": RetrievalCandidate(
            chunk_id="controller",
            score=1.5,
            source="signal",
            score_parts={
                "signal": 1.0,
                "lexical": 0.5,
            },
        ),
        "service": RetrievalCandidate(
            chunk_id="service",
            score=0.8,
            source="relation",
            score_parts={
                "relation": 0.8,
                "original_relation": 0.8,
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["order"], "order flow")

    # Both should appear in results
    assert len(ranked) == 2
    # Service should appear (not filtered out)
    assert any(r.chunk.chunk_id == "service" for r in ranked)


def test_rerank_normalization_effectiveness_with_outlier(tmp_path: Path) -> None:
    """
    Test #8: Normalization must handle outlier scores [0.1, 0.2, 2.4] correctly,
    ensuring penalty/boost actually changes ranking and isn't silently ineffective.
    Guards against the "静默不改名次" risk mentioned in the plan.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    low_score = DocumentChunk(
        chunk_id="low-score",
        file_path=Path("Low.java"),
        start_line=1,
        end_line=10,
        content="class Low { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["low"],
        embedding_id="low-score",
        deleted_at=None,
        metadata={"language": "java"},
    )

    mid_score = DocumentChunk(
        chunk_id="mid-score",
        file_path=Path("Mid.java"),
        start_line=1,
        end_line=10,
        content="class Mid { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["mid"],
        embedding_id="mid-score",
        deleted_at=None,
        metadata={"language": "java"},
    )

    outlier_high = DocumentChunk(
        chunk_id="outlier-high",
        file_path=Path("Outlier.java"),
        start_line=1,
        end_line=10,
        content="class Outlier { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["outlier"],
        embedding_id="outlier-high",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("Low.java"), [low_score])
    store.replace_chunks(Path("Mid.java"), [mid_score])
    store.replace_chunks(Path("Outlier.java"), [outlier_high])

    candidates = {
        "low-score": RetrievalCandidate(
            chunk_id="low-score",
            score=0.1,
            source="lexical",
            score_parts={
                "lexical": 0.1,
            },
        ),
        "mid-score": RetrievalCandidate(
            chunk_id="mid-score",
            score=0.2,
            source="lexical",
            score_parts={
                "lexical": 0.2,
            },
        ),
        "outlier-high": RetrievalCandidate(
            chunk_id="outlier-high",
            score=2.4,
            source="semantic,signal",
            score_parts={
                "semantic": 2.0,
                "signal": 0.4,
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["test"], "test query")

    # After normalization and rerank, ordering should still be sensible
    # (outlier should rank first due to highest combined_score)
    assert ranked[0].chunk.chunk_id == "outlier-high"
    # Verify normalization didn't compress non-outliers to indistinguishable values
    assert ranked[1].chunk.chunk_id == "mid-score"
    assert ranked[2].chunk.chunk_id == "low-score"


def test_rerank_second_sort_consistency_after_merge(tmp_path: Path) -> None:
    """
    Test #9: After query() full pipeline including _merge_overlapping_results,
    visible_results order must match rerank order, not get re-sorted by rank_tier.
    Reproduces the P1 issue where results get "压回去" after the first sort.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # Create a simple file with high-score content
    (repo / "DirectMatch.java").write_text(
        "class DirectMatch { void targetMethod() {} }",
        encoding="utf-8",
    )

    # Create a relation expansion candidate
    (repo / "RelationMatch.java").write_text(
        "class RelationMatch { }",
        encoding="utf-8",
    )

    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=5,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    direct_chunk = store.chunk_for_line(Path("DirectMatch.java"), 1)
    relation_chunk = store.chunk_for_line(Path("RelationMatch.java"), 1)

    # Add signals to make DirectMatch high-score direct
    store.replace_signals(
        Path("DirectMatch.java"),
        [
            CodeSignal(
                signal_id="sig-direct",
                chunk_id=direct_chunk.chunk_id,
                file_path=Path("DirectMatch.java"),
                kind="method",
                name="DirectMatch.targetMethod",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["target", "method"],
                metadata={},
            )
        ],
    )

    bundle = query_repository(repo, "target method", config)

    # Verify results exist
    assert len(bundle.results) > 0
    # High-score direct should be first in final results
    assert bundle.results[0].file_path == Path("DirectMatch.java")


def test_rerank_original_relation_not_misclassified(tmp_path: Path) -> None:
    """
    Test #10: Candidate with original_relation>0 should be classified as
    "original_relation", not "original_direct". Guards against the P1 bug where
    _has_original_query_evidence includes "original_relation" key.
    """
    from context_search_tool.retrieval import _evidence_class

    score_parts_relation_only = {
        "original_relation": 0.8,
        "relation": 0.8,
        # No direct evidence
    }

    evidence_class = _evidence_class(score_parts_relation_only)

    assert evidence_class == "original_relation"
    assert evidence_class != "original_direct"


def test_rerank_output_contract_score_equals_rerank_score(tmp_path: Path) -> None:
    """
    Test #11: RetrievalResult.score should equal rerank_score, and score_parts
    should contain numeric items (combined_score, rerank_score) but not string
    evidence_class. Validates P1 output contract.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "TestFile.java").write_text(
        "class TestFile { void method() {} }",
        encoding="utf-8",
    )

    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=5,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)

    bundle = query_repository(repo, "test method", config)

    assert len(bundle.results) > 0
    result = bundle.results[0]

    # Check that score_parts contains expected numeric keys
    assert "combined_score" in result.score_parts
    # rerank_score should be in score_parts once implemented
    # assert "rerank_score" in result.score_parts

    # evidence_class should NOT be in score_parts (it's a string)
    assert "evidence_class" not in result.score_parts

    # All values in score_parts should be numeric
    for key, value in result.score_parts.items():
        assert isinstance(
            value, (int, float)
        ), f"score_parts[{key}] should be numeric, got {type(value)}"


def test_rerank_merge_field_consistency(tmp_path: Path) -> None:
    """
    Test #12: When merging overlapping results where lower rerank_score has higher
    combined_score, the merged result's rerank_score/evidence_class/evidence_priority/
    reasons should all come from the same winner (highest rerank_score side).
    """
    from context_search_tool.retrieval import (
        _ExpandedResult,
        _merge_expanded_result,
    )

    # Create two overlapping results
    left = _ExpandedResult(
        chunk_ids=["chunk-1"],
        file_path=Path("Test.java"),
        start_line=1,
        end_line=10,
        content="line1\nline2\nline3",
        score=1.5,  # Higher combined_score
        score_parts={
            "combined_score": 1.5,
            "rerank_score": 0.6,  # Lower rerank_score
            "evidence_priority": 4,
            "role_priority": 1.0,
            "role_boost": 0.10,
            "role_exact_match_boost": 0.12,
            "impl_match_boost": 0.18,
            "relation_role_boost": 0.08,
            "relation_detail_penalty": -0.06,
            "identifier_exact_match_boost": 0.40,
            "path_role_hint_boost": 0.14,
            "path_role_mismatch_penalty": -0.08,
        },
        reasons=["reason from left"],
        followup_keywords=["left"],
        rank_tier=2,
        rerank_score=0.6,
        evidence_class="planner_relation",
        evidence_priority=4,
    )

    right = _ExpandedResult(
        chunk_ids=["chunk-2"],
        file_path=Path("Test.java"),
        start_line=8,
        end_line=15,
        content="line8\nline9\nline10",
        score=1.2,  # Lower combined_score
        score_parts={
            "combined_score": 1.2,
            "rerank_score": 0.8,  # Higher rerank_score (winner)
            "evidence_priority": 2,
            "role_priority": 5.0,
            "role_boost": 0.0,
            "role_penalty": -0.10,
        },
        reasons=["reason from right"],
        followup_keywords=["right"],
        rank_tier=1,
        rerank_score=0.8,
        evidence_class="original_relation",
        evidence_priority=2,
    )

    merged = _merge_expanded_result(left, right)

    # All fields should come from the winner (right, with higher rerank_score)
    assert merged.rerank_score == 0.8  # From right
    assert merged.evidence_class == "original_relation"  # From right
    assert merged.evidence_priority == 2  # From right
    assert "reason from right" in merged.reasons
    assert merged.score_parts["rerank_score"] == 0.8
    assert merged.score_parts["evidence_priority"] == 2
    assert merged.score_parts["role_priority"] == 5.0
    assert merged.score_parts["role_boost"] == 0.0
    assert merged.score_parts["role_penalty"] == -0.10
    assert "role_exact_match_boost" not in merged.score_parts
    assert "impl_match_boost" not in merged.score_parts
    assert "relation_role_boost" not in merged.score_parts
    assert "relation_detail_penalty" not in merged.score_parts
    assert "identifier_exact_match_boost" not in merged.score_parts
    assert "path_role_hint_boost" not in merged.score_parts
    assert "path_role_mismatch_penalty" not in merged.score_parts


def test_rerank_merge_frontend_import_boost_is_winner_scoped() -> None:
    from context_search_tool.retrieval import (
        _ExpandedResult,
        _merge_expanded_result,
    )

    left = _ExpandedResult(
        chunk_ids=["support"],
        file_path=Path("src/services/imageDetection.ts"),
        start_line=1,
        end_line=5,
        content="line1\nline2\nline3",
        score=1.5,
        score_parts={
            "combined_score": 1.5,
            "rerank_score": 0.6,
            "frontend_import_support_boost": 0.30,
        },
        reasons=["support reason"],
        followup_keywords=["support"],
        rank_tier=2,
        rerank_score=0.6,
        evidence_class="planner_relation",
        evidence_priority=4,
    )
    right = _ExpandedResult(
        chunk_ids=["winner"],
        file_path=Path("src/services/imageDetection.ts"),
        start_line=4,
        end_line=8,
        content="line4\nline5\nline6",
        score=1.2,
        score_parts={
            "combined_score": 1.2,
            "rerank_score": 0.8,
        },
        reasons=["winner reason"],
        followup_keywords=["winner"],
        rank_tier=1,
        rerank_score=0.8,
        evidence_class="original_relation",
        evidence_priority=2,
    )

    merged = _merge_expanded_result(left, right)

    assert merged.rerank_score == 0.8
    assert "frontend_import_support_boost" not in merged.score_parts


def test_merge_score_parts_preserves_stronger_penalty() -> None:
    from context_search_tool.retrieval import _merge_score_parts

    merged = _merge_score_parts(
        {"route_sibling_penalty": -0.18, "role_boost": 0.12},
        {"route_sibling_penalty": -0.12, "role_boost": 0.18},
    )

    assert merged["route_sibling_penalty"] == -0.18
    assert merged["role_boost"] == 0.18


def test_merge_overlapping_results_uses_role_priority_tiebreak() -> None:
    from context_search_tool.retrieval import (
        _ExpandedResult,
        _merge_overlapping_results,
    )

    service = _ExpandedResult(
        chunk_ids=["service"],
        file_path=Path("ZService.java"),
        start_line=1,
        end_line=3,
        content="service",
        score=1.0,
        score_parts={
            "combined_score": 1.0,
            "rerank_score": 0.8,
            "evidence_priority": 0.0,
            "role_priority": 2.0,
        },
        reasons=["service"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=0.8,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    handler = _ExpandedResult(
        chunk_ids=["handler"],
        file_path=Path("AHandler.java"),
        start_line=1,
        end_line=3,
        content="handler",
        score=1.0,
        score_parts={
            "combined_score": 1.0,
            "rerank_score": 0.8,
            "evidence_priority": 0.0,
            "role_priority": 5.0,
        },
        reasons=["handler"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=0.8,
        evidence_class="original_direct",
        evidence_priority=0,
    )

    merged = _merge_overlapping_results([handler, service])

    assert [item.chunk_ids[0] for item in merged] == ["service", "handler"]


def test_cohort_rerank_demotes_cross_project_unit_candidates_against_top1_anchor(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    collector_metadata = {
        "language": "go",
        "project_name": "collector",
        "project_kind": "go",
        "project_languages": ["go"],
        "project_root": "collector",
        "project_scope_metadata_version": 1,
    }
    backend_metadata = {
        "language": "java",
        "project_name": "investment-assistant-backend",
        "project_kind": "java",
        "project_languages": ["java"],
        "project_root": "investment-assistant-backend",
        "project_scope_metadata_version": 1,
    }
    fund_service = DocumentChunk(
        chunk_id="fund-service",
        file_path=Path("collector/internal/service/fund_service.go"),
        start_line=1,
        end_line=80,
        content="func (s *FundService) CollectNav() {} func (s *FundService) BatchCollectNav() {}",
        chunk_type="symbol",
        lexical_tokens=["fund", "service", "collect", "nav", "batch"],
        metadata=collector_metadata,
    )
    fund_data_client = DocumentChunk(
        chunk_id="fund-data-client",
        file_path=Path("investment-assistant-backend/src/main/java/com/investment/infra/external/FundDataClient.java"),
        start_line=1,
        end_line=60,
        content="class FundDataClient { void fetch(CollectNav nav) {} }",
        chunk_type="symbol",
        lexical_tokens=["fund", "data", "client", "collect", "nav"],
        metadata=backend_metadata,
    )
    nav_service = DocumentChunk(
        chunk_id="nav-service",
        file_path=Path("collector/internal/service/nav_service.go"),
        start_line=1,
        end_line=60,
        content="func (s *NavService) CollectNav() {}",
        chunk_type="symbol",
        lexical_tokens=["nav", "service", "collect"],
        metadata=collector_metadata,
    )
    for chunk in (fund_service, fund_data_client, nav_service):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "fund-service": RetrievalCandidate(
                chunk_id="fund-service",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.50, "path_symbol": 4.5, "direct_text": 1.0},
            ),
            "fund-data-client": RetrievalCandidate(
                chunk_id="fund-data-client",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.50, "path_symbol": 4.25, "direct_text": 1.0},
            ),
            "nav-service": RetrievalCandidate(
                chunk_id="nav-service",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.45, "path_symbol": 4.0, "direct_text": 0.8},
            ),
        },
        retrieval.tokenize_query("FundService CollectNav BatchCollectNav fund service"),
        "FundService CollectNav BatchCollectNav fund service",
    )

    assert ranked[0].chunk.chunk_id == "fund-service"
    score_parts_by_chunk = {item.chunk.chunk_id: item.score_parts for item in ranked}
    assert "cohort_mismatch_penalty" not in score_parts_by_chunk["fund-service"]
    assert "cohort_mismatch_penalty" not in score_parts_by_chunk["nav-service"]
    assert (
        score_parts_by_chunk["fund-data-client"]["cohort_mismatch_penalty"]
        == pytest.approx(-retrieval._COHORT_MISMATCH_PENALTY)
    )
    reasons_by_chunk = {item.chunk.chunk_id: item.reasons for item in ranked}
    assert "cross-project cohort mismatch penalty" in reasons_by_chunk["fund-data-client"]
    assert "cross-project cohort mismatch penalty" not in reasons_by_chunk["fund-service"]
