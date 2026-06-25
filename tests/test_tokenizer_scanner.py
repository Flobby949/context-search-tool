from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool import scanner
from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.scanner import scan_workspace
from context_search_tool.tokenizer import tokenize_identifier, tokenize_query


def test_identifier_tokenizer_splits_common_code_shapes() -> None:
    assert tokenize_identifier("PageAppCatalogQueryExe") == [
        "page",
        "app",
        "catalog",
        "query",
        "exe",
    ]
    assert tokenize_identifier("canApply") == ["can", "apply"]
    assert tokenize_identifier("app_org_region_code") == ["app", "org", "region", "code"]
    assert tokenize_identifier("/apply/audit/pageEs") == ["apply", "audit", "page", "es"]


def test_query_tokenizer_keeps_code_like_terms() -> None:
    tokens = tokenize_query('/apply/audit/pageEs INVOLVED_BY_ME 为什么跨区域')
    assert "apply" in tokens
    assert "audit" in tokens
    assert "page" in tokens
    assert "es" in tokens
    assert "involved" in tokens
    assert "region" not in tokens


def test_query_tokenizer_adds_cjk_search_ngrams() -> None:
    tokens = tokenize_query("工作台相关代码")

    assert "工作台相关代码" in tokens
    assert "工作台" in tokens
    assert "相关" in tokens
    assert "代码" in tokens


def test_query_tokenizer_does_not_add_hardcoded_cjk_code_aliases() -> None:
    tokens = tokenize_query("apaas工作流相关接口")

    assert "apaas" in tokens
    assert "工作流" in tokens
    assert "process" not in tokens
    assert "workflow" not in tokens
    assert "流程" not in tokens
    assert "api" not in tokens
    assert "endpoint" not in tokens


def test_query_tokenizer_does_not_alias_approval_to_audit_terms() -> None:
    tokens = tokenize_query("待我审批")

    assert "审批" in tokens
    assert "审核" not in tokens
    assert "audit" not in tokens


@pytest.mark.parametrize(
    ("query", "forbidden_aliases"),
    [
        ("设备告警", {"alarm", "alert"}),
        ("开门控制", {"open", "door", "access", "control"}),
        ("驿站设备列表", {"station", "device", "equipment", "list"}),
        ("发布意见反馈 发送短信", {"feedback", "sms", "send"}),
        ("账号密码登录注册", {"account", "password", "login", "register", "auth"}),
        ("IOT设备状态", {"device", "control", "status", "state"}),
        ("用户登录认证", {"user", "login", "auth", "authentication"}),
    ],
)
def test_query_tokenizer_does_not_add_java_business_cjk_code_aliases(
    query: str,
    forbidden_aliases: set[str],
) -> None:
    tokens = set(tokenize_query(query))

    assert tokens.isdisjoint(forbidden_aliases)


def test_scanner_respects_gitignore_and_context_search(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("ignored.java\n", encoding="utf-8")
    (repo / "A.java").write_text("class A {}\n", encoding="utf-8")
    (repo / "ignored.java").write_text("class Ignored {}\n", encoding="utf-8")
    (repo / ".context-search").mkdir()
    (repo / ".context-search" / "index.sqlite").write_text("x", encoding="utf-8")

    files = scan_workspace(repo, DEFAULT_CONFIG)

    assert [item.path for item in files] == [Path("A.java")]
    assert files[0].language == "java"
    assert files[0].size > 0
    assert len(files[0].sha256) == 64


def test_scanner_recognizes_common_source_language_suffixes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        "cmd/server/main.go": ("package main\nfunc main() {}\n", "go"),
        "src/lib.rs": ("pub fn handle_upload() {}\n", "rust"),
        "src/App.kt": ("class App\n", "kotlin"),
        "src/Program.cs": ("class Program {}\n", "csharp"),
        "src/server.cpp": ("int main() { return 0; }\n", "cpp"),
        "include/server.hpp": ("class Server {};\n", "cpp"),
        "src/legacy.c": ("int legacy(void) { return 0; }\n", "c"),
        "include/legacy.h": ("int legacy(void);\n", "c"),
        "src/index.php": ("<?php function upload() {}\n", "php"),
        "lib/task.rb": ("def upload_image\nend\n", "ruby"),
        "scripts/deploy.sh": ("#!/usr/bin/env bash\necho deploy\n", "shell"),
        "sql/schema.sql": ("create table images(id bigint);\n", "sql"),
        "Sources/App.swift": ("struct App {}\n", "swift"),
        "Resources/Info.plist": ("<plist><dict></dict></plist>\n", "xml"),
        "App.xcodeproj/project.pbxproj": ("// !$*UTF8*$!\n", "xcodeproj"),
        "App.xcodeproj/xcshareddata/xcschemes/App.xcscheme": (
            "<Scheme></Scheme>\n",
            "xml",
        ),
        "App.xcodeproj/project.xcworkspace/contents.xcworkspacedata": (
            "<Workspace></Workspace>\n",
            "xml",
        ),
        "src/App.scala": ("class App\n", "scala"),
        "lib/main.dart": ("void main() {}\n", "dart"),
        "src/plugin.lua": ("function upload() end\n", "lua"),
        "src/App.vue": ("<script setup>const upload = true</script>\n", "vue"),
        "src/Widget.svelte": ("<script>let upload = true;</script>\n", "svelte"),
    }
    for relative_path, (content, _language) in files.items():
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    scanned = scan_workspace(repo, DEFAULT_CONFIG)

    languages_by_path = {item.path.as_posix(): item.language for item in scanned}
    assert languages_by_path == {
        relative_path: language for relative_path, (_content, language) in files.items()
    }


def test_scanner_indexes_common_lockfiles_for_noise_demotion(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        "Cargo.lock": "[[package]]\nname = \"demo\"\n",
        "yarn.lock": "left-pad@^1.0.0:\n  version \"1.0.0\"\n",
        "go.sum": "example.com/lib v1.0.0 h1:abc\n",
        "package-lock.json": "{\"packages\": {}}\n",
        "pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
        "pnpm-lock.yml": "lockfileVersion: '9.0'\n",
    }
    for relative_path, content in files.items():
        (repo / relative_path).write_text(content, encoding="utf-8")

    scanned = scan_workspace(repo, DEFAULT_CONFIG)

    paths = {item.path.as_posix() for item in scanned}
    assert paths == set(files)
    assert {item.language for item in scanned} == {"lockfile"}


def test_scanner_marks_cross_language_test_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        "service/upload_test.go": "package service\nfunc TestUpload() {}\n",
        "src/components/upload.test.ts": "test('upload', () => {})\n",
        "src/components/upload.spec.tsx": "test('upload', () => {})\n",
        "tests/integration/upload.rs": "#[test]\nfn upload() {}\n",
        "src/main/java/com/example/UploadTest.java": "class UploadTest {}\n",
        "src/main/java/com/example/UploadService.java": "class UploadService {}\n",
    }
    for relative_path, content in files.items():
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    scanned = scan_workspace(repo, DEFAULT_CONFIG)
    by_path = {item.path.as_posix(): item for item in scanned}

    assert by_path["service/upload_test.go"].is_test
    assert by_path["src/components/upload.test.ts"].is_test
    assert by_path["src/components/upload.spec.tsx"].is_test
    assert by_path["tests/integration/upload.rs"].is_test
    assert by_path["src/main/java/com/example/UploadTest.java"].is_test
    assert not by_path["src/main/java/com/example/UploadService.java"].is_test


def test_scanner_skips_all_hidden_paths_by_default(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "README.md").write_text("# Visible docs\n", encoding="utf-8")
    src = repo / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "App.java").write_text("class App {}\n", encoding="utf-8")
    config_dir = repo / "config"
    config_dir.mkdir()
    (config_dir / "broker.properties").write_text(
        "brokerPort=9999\n",
        encoding="utf-8",
    )

    qoder_docs = repo / ".qoder" / "repowiki"
    qoder_docs.mkdir(parents=True)
    (qoder_docs / "Notes.md").write_text("# Generated notes\n", encoding="utf-8")
    github_workflow = repo / ".github" / "workflows"
    github_workflow.mkdir(parents=True)
    (github_workflow / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (repo / ".hidden.yml").write_text("hidden: true\n", encoding="utf-8")

    files = scan_workspace(repo, DEFAULT_CONFIG)

    assert [item.path for item in files] == [
        Path("README.md"),
        Path("config/broker.properties"),
        Path("src/main/java/App.java"),
    ]


def test_scanner_skips_default_dependency_and_build_directories(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "App.ts").write_text("export const app = true\n", encoding="utf-8")

    for dirname in ("node_modules", "vendor", ".venv", "dist", "build", "target"):
        directory = repo / dirname
        directory.mkdir()
        (directory / "Noise.ts").write_text(
            "export const noise = true\n",
            encoding="utf-8",
        )

    files = scan_workspace(repo, DEFAULT_CONFIG)

    assert [item.path for item in files] == [Path("src/App.ts")]


def test_scanner_include_patterns_do_not_override_default_skips(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "App.ts").write_text("export const app = true\n", encoding="utf-8")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "Noise.ts").write_text(
        "export const noise = true\n",
        encoding="utf-8",
    )
    config = replace(
        DEFAULT_CONFIG,
        index=replace(
            DEFAULT_CONFIG.index,
            include=["src/**/*.ts", "node_modules/**/*.ts"],
        ),
    )

    files = scan_workspace(repo, config)

    assert [item.path for item in files] == [Path("src/App.ts")]


def test_scanner_respects_include_patterns(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    src = repo / "src"
    docs = repo / "docs"
    src.mkdir()
    docs.mkdir()
    (src / "Service.java").write_text("class Service {}\n", encoding="utf-8")
    (docs / "Notes.md").write_text("# Notes\n", encoding="utf-8")
    config = replace(
        DEFAULT_CONFIG,
        index=replace(DEFAULT_CONFIG.index, include=["src/**/*.java"]),
    )

    files = scan_workspace(repo, config)

    assert [item.path for item in files] == [Path("src/Service.java")]


def test_scanner_returns_files_sorted_by_relative_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = repo / "a"
    nested.mkdir()
    (repo / "b.java").write_text("class B {}\n", encoding="utf-8")
    (nested / "c.java").write_text("class C {}\n", encoding="utf-8")

    files = scan_workspace(repo, DEFAULT_CONFIG)

    assert [item.path for item in files] == [Path("a/c.java"), Path("b.java")]


def test_scanner_skips_unreadable_candidate_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    readable = repo / "Readable.java"
    unreadable = repo / "Unreadable.java"
    readable.write_text("class Readable {}\n", encoding="utf-8")
    unreadable.write_text("class Unreadable {}\n", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path == unreadable:
            raise PermissionError("cannot read")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    files = scan_workspace(repo, DEFAULT_CONFIG)

    assert [item.path for item in files] == [Path("Readable.java")]


def test_scanner_prunes_ignored_and_excluded_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (repo / "A.java").write_text("class A {}\n", encoding="utf-8")
    ignored = repo / "ignored"
    ignored.mkdir()
    (ignored / "Ignored.java").write_text("class Ignored {}\n", encoding="utf-8")
    excluded = repo / "excluded"
    excluded.mkdir()
    (excluded / "Excluded.java").write_text("class Excluded {}\n", encoding="utf-8")
    original_walk = scanner.os.walk

    def walk(path: Path):
        for dirpath, dirnames, filenames in original_walk(path):
            if Path(dirpath) in {ignored, excluded}:
                raise AssertionError("ignored or excluded directory was descended into")
            yield dirpath, dirnames, filenames

    monkeypatch.setattr(scanner.os, "walk", walk)
    config = replace(
        DEFAULT_CONFIG,
        index=replace(DEFAULT_CONFIG.index, exclude=["excluded/"]),
    )

    files = scan_workspace(repo, config)

    assert [item.path for item in files] == [Path("A.java")]


def test_scanner_broad_language_support_still_skips_ignored_binary_and_oversized_files(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("ignored.go\n", encoding="utf-8")
    (repo / "visible.go").write_text(
        "package main\nfunc visible() {}\n",
        encoding="utf-8",
    )
    (repo / "ignored.go").write_text(
        "package main\nfunc ignored() {}\n",
        encoding="utf-8",
    )
    (repo / "binary.go").write_bytes(b"package main\x00func binary() {}\n")
    (repo / "large.go").write_text(
        "x" * (DEFAULT_CONFIG.index.max_file_bytes + 1),
        encoding="utf-8",
    )

    files = scan_workspace(repo, DEFAULT_CONFIG)

    assert [item.path for item in files] == [Path("visible.go")]
    assert files[0].language == "go"
