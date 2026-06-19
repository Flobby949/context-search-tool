# Generic Language Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CST's generic baseline index and retrieve source code across common programming languages, so projects like Go `imagebed` are usable even before language-specific framework plugins exist.

**Architecture:** Keep language-specific framework understanding as an enhancement layer. The baseline scanner should recognize common source-code suffixes, the existing generic chunker/tokenizer should index those files, and retrieval acceptance tests should prove source files are found by code-like queries without requiring a dedicated plugin.

**Tech Stack:** Python 3.11+, pytest, existing scanner/chunker/tokenizer/indexer/retrieval pipeline, BGE-M3 local smoke workflow when available.

---

## 1. Problem Statement

The current scanner only recognizes a small suffix set:

```python
{
    ".java": "java",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".xml": "xml",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".properties": "properties",
}
```

That makes CST unusable as a generic code retrieval baseline on common projects such as `/Users/flobby/vibe_coding/imagebed`, where all `.go` source files are skipped and only README/config documents are indexed:

```text
Indexed 6 files
Symbols: 0
Indexed files: DEPLOY.md, README.md, TYPORA.md, cmd/typora/README.md, config.yaml, docker-compose.yml
```

This is not a Java/Spring ranking issue. It is a baseline language-coverage gap. The first fix should be broad source-file scanning and generic retrieval, not a Go/Gin plugin.

## 2. Scope

### In Scope

- Expand scanner language suffix coverage for common programming languages and source-adjacent files.
- Keep binary, generated, hidden, ignored, oversized, and explicitly excluded files skipped.
- Add focused scanner tests proving broad language suffixes are recognized.
- Add generic index/retrieval tests proving non-plugin languages such as Go and Rust are indexed and searchable.
- Add a real-project smoke checklist for `/Users/flobby/vibe_coding/imagebed`.
- Document the difference between generic baseline support and language/framework plugins.

### Out Of Scope

- Do not add Go/Gin route parsing in this task.
- Do not add framework-specific plugins for Rust, PHP, Ruby, C#, or other languages.
- Do not change `DocumentChunk`, MCP payload shape, or manifest schema.
- Do not change embedding defaults or BGE-M3 configuration.
- Do not add business alias maps or repo-specific search shortcuts.
- Do not tune Java/Spring reranking in this task.

## 3. Target Semantics

After implementation:

- `.go`, `.rs`, `.kt`, `.cs`, `.cpp`, `.hpp`, `.c`, `.h`, `.php`, `.rb`, `.sh`, `.sql`, `.swift`, `.scala`, `.dart`, `.lua`, and similar common source files are scanned by default.
- A Go project without a Go plugin still indexes code files as generic chunks.
- Querying `UploadHandler MultiUpload multipart file storage Save` can return `handler/upload.go`.
- Querying `AuthMiddleware Authorization Bearer token AdminMiddleware` can return `middleware/auth.go`.
- Querying `NewS3Storage NewOSSStorage NewLocalStorage initStorage` can return `main.go` and `storage/*.go`.
- `symbols` may remain `0` for languages without plugins. That is acceptable for this baseline if file/chunk retrieval works.

## 4. Files And Responsibilities

- Modify: `src/context_search_tool/scanner.py`
  - Owns suffix-to-language mapping and scanning eligibility.
- Modify: `tests/test_tokenizer_scanner.py`
  - Owns scanner behavior tests, including broad suffix recognition and ignore/exclude behavior.
- Modify: `tests/test_indexer_manifest.py`
  - Owns indexer integration tests proving non-plugin source files are indexed.
- Modify: `tests/test_retrieval_pipeline.py`
  - Owns retrieval acceptance tests proving generic source files can be found by code-like queries.
- Modify: `README.md`
  - Documents generic language coverage and clarifies that framework path graphs are plugin-level enhancements.

## 5. Implementation Tasks

### Task 1: Expand Scanner Language Suffix Coverage

**Files:**
- Modify: `src/context_search_tool/scanner.py`
- Modify: `tests/test_tokenizer_scanner.py`

- [ ] **Step 1: Write a failing scanner coverage test**

Add this test to `tests/test_tokenizer_scanner.py` near the existing scanner tests:

```python
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
```

- [ ] **Step 2: Run the failing scanner coverage test**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_tokenizer_scanner.py::test_scanner_recognizes_common_source_language_suffixes -q
```

Expected before implementation:

```text
FAILED ... assert languages_by_path == ...
```

The failure should show that many paths are missing because their suffixes are not recognized.

- [ ] **Step 3: Implement broad suffix coverage**

Replace `_LANGUAGES_BY_SUFFIX` in `src/context_search_tool/scanner.py` with this mapping:

```python
_LANGUAGES_BY_SUFFIX = {
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".go": "go",
    ".rs": "rust",
    ".py": "python",
    ".pyw": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".vue": "vue",
    ".svelte": "svelte",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".fs": "fsharp",
    ".fsx": "fsharp",
    ".swift": "swift",
    ".plist": "xml",
    ".pbxproj": "xcodeproj",
    ".xcscheme": "xml",
    ".xcworkspacedata": "xml",
    ".php": "php",
    ".rb": "ruby",
    ".rake": "ruby",
    ".lua": "lua",
    ".dart": "dart",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".r": "r",
    ".m": "objectivec",
    ".mm": "objectivecpp",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".ps1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    ".sql": "sql",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".proto": "protobuf",
    ".thrift": "thrift",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".jsonc": "json",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "config",
    ".env": "env",
    ".md": "markdown",
    ".mdx": "mdx",
    ".rst": "restructuredtext",
    ".properties": "properties",
}
```

Keep `_language_for_path(path: Path) -> str` unchanged:

```python
def _language_for_path(path: Path) -> str:
    return _LANGUAGES_BY_SUFFIX.get(path.suffix.lower(), "")
```

This treats uppercase `.R` as lowercase `.r` because `path.suffix.lower()` is already used.

- [ ] **Step 4: Run scanner tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_tokenizer_scanner.py -q
```

Expected:

```text
passed
```

The exact count may change as tests are added.

### Task 2: Prove Generic Indexing For Non-Plugin Languages

**Files:**
- Modify: `tests/test_indexer_manifest.py`

- [ ] **Step 1: Write a failing Go indexing test**

Add this test to `tests/test_indexer_manifest.py`:

```python
def test_index_repository_indexes_go_source_with_generic_chunks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "handler" / "upload.go"
    source.parent.mkdir(parents=True)
    source.write_text(
        """
package handler

type UploadHandler struct {}

func (h *UploadHandler) Upload() string {
    return "upload"
}

func (h *UploadHandler) MultiUpload() string {
    return "multi"
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_seen == 1
    assert summary.files_indexed == 1
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    stats = store.stats()
    assert stats["source_files"] == 1
    assert stats["active_chunks"] >= 1
    chunk = store.chunk_for_line(Path("handler/upload.go"), 5)
    assert chunk.chunk_type == "generic"
    assert chunk.metadata["language"] == "go"
    assert "upload" in chunk.lexical_tokens
    assert "handler" in chunk.lexical_tokens
```

- [ ] **Step 2: Run the failing Go indexing test**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_indexer_manifest.py::test_index_repository_indexes_go_source_with_generic_chunks -q
```

Expected before Task 1 implementation:

```text
FAILED ... assert summary.files_seen == 1
```

Expected after Task 1 implementation:

```text
1 passed
```

- [ ] **Step 3: Write a Rust indexing guard test**

Add this test to the same file:

```python
def test_index_repository_indexes_rust_source_with_generic_chunks(tmp_path: Path) -> None:
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
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_seen == 1
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    chunk = store.chunk_for_line(Path("src/lib.rs"), 4)
    assert chunk.metadata["language"] == "rust"
    assert "delete" in chunk.lexical_tokens
    assert "filename" in chunk.lexical_tokens
```

- [ ] **Step 4: Run focused indexer tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_indexer_manifest.py::test_index_repository_indexes_go_source_with_generic_chunks tests/test_indexer_manifest.py::test_index_repository_indexes_rust_source_with_generic_chunks -q
```

Expected:

```text
2 passed
```

### Task 3: Prove Generic Retrieval Finds Non-Plugin Source Files

**Files:**
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add a generic Go fixture helper**

Add these helpers near other retrieval fixture helpers in `tests/test_retrieval_pipeline.py`:

```python
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
```

- [ ] **Step 2: Write a failing retrieval test for Go upload code**

Add this test:

```python
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
```

- [ ] **Step 3: Write retrieval tests for auth and storage paths**

Add:

```python
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
```

Add:

```python
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
    assert any(path in paths for path in ["storage/local.go", "storage/oss.go", "storage/s3.go"])
```

- [ ] **Step 4: Write a generic Rust retrieval test**

Add:

```python
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
```

- [ ] **Step 5: Run the failing generic retrieval tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py::test_generic_retrieval_finds_go_upload_handler_without_language_plugin tests/test_retrieval_pipeline.py::test_generic_retrieval_finds_go_auth_middleware_without_language_plugin tests/test_retrieval_pipeline.py::test_generic_retrieval_finds_go_storage_backends_without_language_plugin tests/test_retrieval_pipeline.py::test_generic_retrieval_finds_rust_source_without_language_plugin -q
```

Expected before Task 1 implementation:

```text
FAILED
```

Expected after Task 1 implementation:

```text
3 passed
```

If any test still fails after Task 1, inspect the result paths and score parts before changing ranking. Do not add Go-specific boosts in this baseline task.

### Task 4: Preserve Ignore, Binary, And Size Safety

**Files:**
- Modify: `tests/test_tokenizer_scanner.py`

- [ ] **Step 1: Add a test that broad coverage still respects ignore and binary safety**

Add:

```python
def test_scanner_broad_language_support_still_skips_ignored_binary_and_oversized_files(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("ignored.go\n", encoding="utf-8")
    (repo / "visible.go").write_text("package main\nfunc visible() {}\n", encoding="utf-8")
    (repo / "ignored.go").write_text("package main\nfunc ignored() {}\n", encoding="utf-8")
    (repo / "binary.go").write_bytes(b"package main\x00func binary() {}\n")
    (repo / "large.go").write_text("x" * (DEFAULT_CONFIG.index.max_file_bytes + 1), encoding="utf-8")

    files = scan_workspace(repo, DEFAULT_CONFIG)

    assert [item.path for item in files] == [Path("visible.go")]
    assert files[0].language == "go"
```

- [ ] **Step 2: Run scanner safety tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_tokenizer_scanner.py::test_scanner_broad_language_support_still_skips_ignored_binary_and_oversized_files tests/test_tokenizer_scanner.py::test_scanner_respects_gitignore_and_context_search tests/test_scanner_prunes_ignored_and_excluded_directories -q
```

Expected:

```text
3 passed
```

If the command cannot find `test_scanner_prunes_ignored_and_excluded_directories`, run the full scanner file instead:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_tokenizer_scanner.py -q
```

### Task 5: Document Generic Baseline Language Coverage

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the capability overview**

In `README.md`, update the capability bullets so generic source coverage is explicit. Replace the current Java-focused limitation wording in the overview with this text:

```markdown
- 通用源码覆盖：默认扫描常见源码后缀，包括 Java、Go、Rust、Python、TypeScript/JavaScript、C/C++、C#、Kotlin、Scala、Swift、PHP、Ruby、Shell、SQL、Dart、Lua 等；没有专用插件的语言会使用通用切块和 token 检索。
- Java 增强：Java/Spring 是第一版框架级信号生产者，可提取 Spring endpoint、JavaDoc/comment、方法调用 usage、短链 relation、class/interface/enum/method/constant、enum value 和 SQL 注解词元。
- 当前限制：通用语言覆盖只保证源码能索引和按文本/token 检索；框架语义如 Go/Gin 路由、Rust/Axum 路由、Spring AI `@Tool` 注册链路需要后续语言或框架插件增强。
```

Do not claim symbol extraction for languages without plugins.

- [ ] **Step 2: Add a short troubleshooting note**

Add this note near the indexing or configuration section:

```markdown
### Generic Language Baseline

If a project uses a language without a dedicated plugin, CST still indexes supported source files as generic chunks. `stats` may show `Symbols: 0`; that is expected when no plugin emits symbols. Code-like queries should still find files by path terms, identifiers, comments, strings, and surrounding source text.

If `cst stats` shows only README/config files for a normal source repository, check whether the source suffix is listed in the scanner language map and add a scanner regression test before tuning ranking.
```

- [ ] **Step 3: Run README grep checks**

Run:

```bash
rg -n "通用源码覆盖|Generic Language Baseline|Symbols: 0|Go、Rust" README.md
```

Expected output includes all four patterns.

### Task 6: Real Project Smoke On `/Users/flobby/vibe_coding/imagebed`

**Files:**
- No source files.
- Runtime side effects in target repo: `.context-search/` and possibly `.gitignore` entry for `.context-search/`.

- [ ] **Step 1: Check target repo state before smoke**

Run:

```bash
cd /Users/flobby/vibe_coding/imagebed
git status --short --branch --untracked-files=normal
```

Expected known side effect from earlier investigation may include:

```text
 M .gitignore
```

Do not revert user changes. If unrelated dirty files appear, note them and continue without touching them.

- [ ] **Step 2: Clean stale CST index only if it is incompatible**

Run:

```bash
PYTHONPATH=/Users/flobby/Documents/context-seatch-tool/src \
/opt/homebrew/Caskroom/miniforge/base/bin/python -m context_search_tool.cli stats /Users/flobby/vibe_coding/imagebed
```

If stats still reports only 6 files after scanner support is implemented, remove only the CST index directory:

```bash
rm -rf /Users/flobby/vibe_coding/imagebed/.context-search
```

Then recreate BGE-M3 config using `apply_patch`:

```patch
*** Begin Patch
*** Add File: /Users/flobby/vibe_coding/imagebed/.context-search/config.toml
+[index]
+include = []
+exclude = []
+max_file_bytes = 500000
+max_full_file_bytes = 200000
+
+[retrieval]
+semantic_top_k = 80
+lexical_top_k = 80
+final_top_k = 12
+context_before_lines = 8
+context_after_lines = 12
+
+[embedding]
+provider = "bge"
+model = "bge-m3:latest"
+dimensions = 1024
+
+[query_planner]
+enabled = false
+provider = "ollama"
+model = "qwen3.5:4b-mlx"
+base_url = "http://localhost:11434"
+use_system_proxy = false
+timeout_seconds = 8.0
+max_rewritten_queries = 4
+max_keywords = 12
+max_symbol_hints = 8
*** End Patch
```

- [ ] **Step 3: Reindex imagebed**

Run:

```bash
PYTHONPATH=/Users/flobby/Documents/context-seatch-tool/src \
/opt/homebrew/Caskroom/miniforge/base/bin/python -m context_search_tool.cli index /Users/flobby/vibe_coding/imagebed
```

Expected after implementation:

```text
Indexed more than 20 files
```

The exact number can vary with ignored files, but it must include `.go` source files.

- [ ] **Step 4: Verify indexed files include Go source**

Run:

```bash
sqlite3 /Users/flobby/vibe_coding/imagebed/.context-search/index.sqlite \
"select path, language from source_files where path in ('main.go','handler/upload.go','middleware/auth.go','storage/local.go','storage/oss.go','storage/s3.go') order by path;"
```

Expected:

```text
handler/upload.go|go
main.go|go
middleware/auth.go|go
storage/local.go|go
storage/oss.go|go
storage/s3.go|go
```

- [ ] **Step 5: Run generic retrieval smoke queries**

Run:

```bash
PYTHONPATH=/Users/flobby/Documents/context-seatch-tool/src \
/opt/homebrew/Caskroom/miniforge/base/bin/python - <<'PY'
from dataclasses import replace
from pathlib import Path

from context_search_tool.config import load_config
from context_search_tool.retrieval import query_repository

repo = Path("/Users/flobby/vibe_coding/imagebed")
config = load_config(repo)
config = replace(config, retrieval=replace(config.retrieval, final_top_k=8))

queries = {
    "upload": "UploadHandler MultiUpload multipart file storage Save",
    "auth": "AuthMiddleware Authorization Bearer token AdminMiddleware",
    "storage": "initStorage NewLocalStorage NewOSSStorage NewS3Storage storage type",
    "delete": "DeleteHandler DeleteByFilename BatchDelete storage Delete",
}

for label, query in queries.items():
    bundle = query_repository(repo, query, config, context_lines=4)
    print(f"## {label}: {query}")
    for index, result in enumerate(bundle.results[:8], 1):
        print(f"{index}. {result.file_path}:{result.start_line}-{result.end_line} score={result.score:.4f}")
    print()
PY
```

Expected result windows:

```text
upload: handler/upload.go appears in top 5
auth: middleware/auth.go appears in top 5
storage: main.go and at least one storage/*.go appears in top 8
delete: handler/delete.go appears in top 5
```

This smoke validates generic baseline usability only. It does not require route graph summaries, symbol counts, or Go/Gin endpoint extraction.

## 6. Verification Checklist

Run these commands before claiming completion:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_tokenizer_scanner.py -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_indexer_manifest.py::test_index_repository_indexes_go_source_with_generic_chunks tests/test_indexer_manifest.py::test_index_repository_indexes_rust_source_with_generic_chunks -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py::test_generic_retrieval_finds_go_upload_handler_without_language_plugin tests/test_retrieval_pipeline.py::test_generic_retrieval_finds_go_auth_middleware_without_language_plugin tests/test_retrieval_pipeline.py::test_generic_retrieval_finds_go_storage_backends_without_language_plugin tests/test_retrieval_pipeline.py::test_generic_retrieval_finds_rust_source_without_language_plugin -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest -q
```

Expected:

```text
all selected tests pass
full test suite passes
```

Then run the real-project imagebed smoke in Task 6 and record:

- files indexed
- chunks indexed
- embedding provider/model/dimensions
- top result paths for upload/auth/storage/delete queries
- target repo git status after smoke

## 7. Risks And Open Questions

- Broad suffix coverage may index more files in large polyglot repos. Existing `max_file_bytes`, `.gitignore`, hidden path skipping, and `exclude` patterns should control this. If performance regresses, add user-configurable excludes rather than removing common languages.
- Some suffixes are ambiguous. `.h` can be C or C++; this plan maps it to `c` for baseline tokenization only. This does not affect generic retrieval quality much because no C/C++ plugin semantics are attached.
- `Symbols: 0` remains expected for languages without plugins. Do not overstate generic support as symbol-aware support.
- If Go retrieval ranks README/config above source after `.go` files are indexed, inspect score parts first. Fix generic document-vs-source ranking only if the issue reproduces across multiple non-Java fixtures.

## 8. Stop Point

Stop after saving this plan. Do not implement until the user explicitly confirms execution.
