# Semantic Retrieval Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first CLI version of a local hybrid semantic retrieval tool that indexes a target repository into `.context-search/` and returns ranked code context bundles.

**Architecture:** The CLI is a thin Typer layer over a reusable core API. Core indexing scans files, chunks content, extracts optional language signals, writes metadata and FTS data to SQLite, writes vectors through a `VectorStore`, and records manifest compatibility. Core retrieval combines semantic, lexical, path, and symbol candidates, then reranks, expands context, and formats Markdown or JSON.

**Tech Stack:** Python 3.11+, Typer, Rich, SQLite FTS5 through `sqlite3`, NumPy, pathspec, httpx, pytest, dataclasses, built-in `tomllib`.

---

## File Structure

Create this project structure:

```text
pyproject.toml
README.md
src/context_search_tool/__init__.py
src/context_search_tool/cli.py
src/context_search_tool/config.py
src/context_search_tool/models.py
src/context_search_tool/paths.py
src/context_search_tool/tokenizer.py
src/context_search_tool/scanner.py
src/context_search_tool/chunker.py
src/context_search_tool/java_plugin.py
src/context_search_tool/plugins.py
src/context_search_tool/sqlite_store.py
src/context_search_tool/manifest.py
src/context_search_tool/embeddings.py
src/context_search_tool/vector_store.py
src/context_search_tool/indexer.py
src/context_search_tool/retrieval.py
src/context_search_tool/formatters.py
tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditController.java
tests/fixtures/java-spring-mini/src/main/java/com/example/audit/EsApplyAuditPageQryExe.java
tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditMapper.java
tests/fixtures/java-spring-mini/src/main/java/com/example/audit/AuditStatus.java
tests/test_cli_import.py
tests/test_config_paths.py
tests/test_tokenizer_scanner.py
tests/test_sqlite_store.py
tests/test_chunker_java_plugin.py
tests/test_embeddings_vector_store.py
tests/test_indexer_manifest.py
tests/test_retrieval_pipeline.py
tests/test_formatters.py
tests/test_cli_commands.py
tests/test_acceptance_java_fixture.py
```

Responsibilities:

- `cli.py`: Typer commands only; no retrieval logic.
- `config.py`: config dataclasses, default TOML rendering, config loading.
- `models.py`: shared dataclasses and typed result objects.
- `paths.py`: repository inference and index path helpers.
- `tokenizer.py`: identifier/path/query tokenization.
- `scanner.py`: file discovery, ignore handling, hash and language detection.
- `chunker.py`: language-neutral chunking and context expansion helpers.
- `java_plugin.py`: Java v0 extraction for package, imports, class/methods, routes, MyBatis annotations, constants, enums.
- `plugins.py`: plugin protocol and registry.
- `sqlite_store.py`: SQLite schema, FTS, chunks, files, symbols, logical deletion, stats.
- `manifest.py`: schema and embedding compatibility manifest.
- `embeddings.py`: embedding provider protocol, deterministic hash provider, OpenAI-compatible provider.
- `vector_store.py`: NumPy-backed vector store with logical deletion filtering.
- `indexer.py`: index creation/update orchestration.
- `retrieval.py`: query normalization, candidate retrieval, merge, rerank, context expansion.
- `formatters.py`: Markdown and JSON output.

---

### Task 1: Project Scaffold And Importable CLI

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/context_search_tool/__init__.py`
- Create: `src/context_search_tool/cli.py`
- Test: `tests/test_cli_import.py`

- [ ] **Step 1: Write the failing import test**

Create `tests/test_cli_import.py`:

```python
from typer.testing import CliRunner

from context_search_tool.cli import app


def test_cli_app_imports_and_shows_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Context Search Tool" in result.output
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_cli_import.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'context_search_tool'`.

- [ ] **Step 3: Add packaging and a minimal CLI**

Create `pyproject.toml`:

```toml
[project]
name = "context-search-tool"
version = "0.1.0"
description = "Local hybrid semantic retrieval for codebases"
requires-python = ">=3.11"
dependencies = [
  "typer>=0.12.0",
  "rich>=13.7.0",
  "pathspec>=0.12.1",
  "numpy>=1.26.0",
  "httpx>=0.27.0"
]

[project.scripts]
cst = "context_search_tool.cli:app"

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0"
]

[build-system]
requires = ["setuptools>=69.0.0"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

Create `README.md`:

```markdown
# Context Search Tool

Local hybrid semantic retrieval for codebases.
```

Create `src/context_search_tool/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `src/context_search_tool/cli.py`:

```python
import typer

app = typer.Typer(
    help="Context Search Tool",
    no_args_is_help=True,
)


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_cli_import.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md src/context_search_tool/__init__.py src/context_search_tool/cli.py tests/test_cli_import.py
git commit -m "feat: scaffold context search CLI"
```

---

### Task 2: Config And Repository Path Handling

**Files:**
- Create: `src/context_search_tool/config.py`
- Create: `src/context_search_tool/paths.py`
- Test: `tests/test_config_paths.py`

- [ ] **Step 1: Write failing tests for config defaults and repo inference**

Create `tests/test_config_paths.py`:

```python
from pathlib import Path

import pytest

from context_search_tool.config import DEFAULT_CONFIG, load_config, render_default_config
from context_search_tool.paths import (
    RepositoryNotFoundError,
    find_repo_root,
    index_dir_for,
    ensure_index_layout,
)


def test_render_default_config_contains_version_one_values() -> None:
    rendered = render_default_config()
    assert "max_file_bytes = 500000" in rendered
    assert "max_full_file_bytes = 200000" in rendered
    assert "semantic_top_k = 80" in rendered
    assert DEFAULT_CONFIG.embedding.provider == "hash"


def test_load_config_creates_default_when_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    ensure_index_layout(repo)

    config = load_config(repo)

    assert config.index.max_file_bytes == 500000
    assert (repo / ".context-search" / "config.toml").exists()


def test_find_repo_root_prefers_existing_index_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    child = repo / "src" / "main"
    child.mkdir(parents=True)
    ensure_index_layout(repo)
    monkeypatch.chdir(child)

    assert find_repo_root(None) == repo


def test_find_repo_root_uses_explicit_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert find_repo_root(repo) == repo
    assert index_dir_for(repo) == repo / ".context-search"


def test_find_repo_root_errors_when_cwd_has_no_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RepositoryNotFoundError):
        find_repo_root(None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config_paths.py -v`

Expected: FAIL because `config.py` and `paths.py` do not exist.

- [ ] **Step 3: Implement config and path helpers**

Create `src/context_search_tool/config.py` with these public objects:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class IndexConfig:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    max_file_bytes: int = 500_000
    max_full_file_bytes: int = 200_000


@dataclass(frozen=True)
class RetrievalConfig:
    semantic_top_k: int = 80
    lexical_top_k: int = 80
    final_top_k: int = 12
    context_before_lines: int = 8
    context_after_lines: int = 12


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "hash"
    model: str = "hash-v1"
    dimensions: int = 384
    base_url: str | None = None
    api_key_env: str | None = None


@dataclass(frozen=True)
class ToolConfig:
    index: IndexConfig = field(default_factory=IndexConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)


DEFAULT_CONFIG = ToolConfig()
```

Add `render_default_config()` and `load_config(repo: Path) -> ToolConfig`. `load_config` must create `.context-search/config.toml` with defaults when it is missing and must parse the three config sections when present.

Create `src/context_search_tool/paths.py` with these public objects:

```python
from __future__ import annotations

from pathlib import Path


class RepositoryNotFoundError(RuntimeError):
    pass
```

Add these functions:

- `index_dir_for(repo: Path) -> Path`
- `ensure_index_layout(repo: Path) -> Path`
- `find_repo_root(explicit: Path | None) -> Path`

`find_repo_root(None)` must walk upward from `Path.cwd()` and accept a directory that contains `.context-search`. It may also accept a Git root containing `.git`, but query commands must still check for the index before querying.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_paths.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/config.py src/context_search_tool/paths.py tests/test_config_paths.py
git commit -m "feat: add repository config and path helpers"
```

---

### Task 3: Tokenizer And Workspace Scanner

**Files:**
- Create: `src/context_search_tool/tokenizer.py`
- Create: `src/context_search_tool/scanner.py`
- Test: `tests/test_tokenizer_scanner.py`

- [ ] **Step 1: Write failing tokenizer and scanner tests**

Create `tests/test_tokenizer_scanner.py`:

```python
from pathlib import Path

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tokenizer_scanner.py -v`

Expected: FAIL because tokenizer and scanner modules do not exist.

- [ ] **Step 3: Implement tokenization**

Create `src/context_search_tool/tokenizer.py` with:

- `tokenize_identifier(value: str) -> list[str]`
- `tokenize_query(value: str) -> list[str]`
- `tokens_for_path(path: Path | str) -> list[str]`

Rules:

- Split slash, dot, colon, hyphen, underscore, whitespace.
- Split camelCase and PascalCase boundaries.
- Lowercase ASCII tokens.
- Preserve non-ASCII words as whole tokens when regex can identify them.
- Drop empty tokens.

- [ ] **Step 4: Implement workspace scanner**

Create `src/context_search_tool/scanner.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ScannedFile:
    path: Path
    absolute_path: Path
    language: str
    sha256: str
    size: int
    mtime_ns: int
    is_generated: bool = False
    is_test: bool = False
    metadata: dict[str, str] = field(default_factory=dict)
```

Add `scan_workspace(repo: Path, config: ToolConfig) -> list[ScannedFile]`.

Scanner rules:

- Always skip `.git` and `.context-search`.
- Read `.gitignore` with `pathspec.PathSpec.from_lines("gitwildmatch", lines)` when present.
- Apply `config.index.exclude` after `.gitignore`.
- Include only regular files.
- Skip files larger than `config.index.max_file_bytes`.
- Skip files that contain a NUL byte in the first 4096 bytes.
- Detect language by extension for at least `.java`, `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.xml`, `.yml`, `.yaml`, `.json`, `.md`, `.properties`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_tokenizer_scanner.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/context_search_tool/tokenizer.py src/context_search_tool/scanner.py tests/test_tokenizer_scanner.py
git commit -m "feat: scan workspaces and tokenize code terms"
```

---

### Task 4: Shared Models And SQLite Store

**Files:**
- Create: `src/context_search_tool/models.py`
- Create: `src/context_search_tool/sqlite_store.py`
- Test: `tests/test_sqlite_store.py`

- [ ] **Step 1: Write failing SQLite store tests**

Create `tests/test_sqlite_store.py`:

```python
from pathlib import Path

from context_search_tool.models import DocumentChunk, SourceFile, SymbolRef
from context_search_tool.sqlite_store import SQLiteStore


def test_store_round_trips_files_chunks_symbols_and_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite"
    store = SQLiteStore(db_path)
    store.initialize()

    source = SourceFile(
        path=Path("src/App.java"),
        language="java",
        sha256="a" * 64,
        size=100,
        mtime_ns=123,
        is_generated=False,
        is_test=False,
        metadata={},
    )
    symbol = SymbolRef(
        name="ApplyAuditController",
        kind="class",
        start_line=1,
        end_line=20,
        language="java",
        metadata={"role": "controller"},
    )
    chunk = DocumentChunk(
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        start_line=1,
        end_line=20,
        content="@PostMapping(\"/apply/audit/pageEs\")\nclass ApplyAuditController {}",
        chunk_type="symbol",
        symbols=[symbol],
        lexical_tokens=["post", "mapping", "apply", "audit", "page", "es"],
        embedding_id="chunk-1",
        deleted_at=None,
        metadata={"route_path": "/apply/audit/pageEs"},
    )

    store.upsert_source_file(source)
    store.replace_chunks(Path("src/App.java"), [chunk])

    matches = store.lexical_search(["apply", "audit"], limit=5)

    assert matches[0].chunk_id == "chunk-1"
    assert store.chunk_for_line(Path("src/App.java"), 3).chunk_id == "chunk-1"


def test_store_marks_removed_file_chunks_deleted(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    chunk = DocumentChunk(
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        start_line=1,
        end_line=2,
        content="class App {}",
        chunk_type="generic",
        symbols=[],
        lexical_tokens=["class", "app"],
        embedding_id="chunk-1",
        deleted_at=None,
        metadata={},
    )
    store.replace_chunks(Path("src/App.java"), [chunk])

    store.mark_file_deleted(Path("src/App.java"))

    assert store.lexical_search(["app"], limit=5) == []
    assert store.deleted_chunk_ids() == {"chunk-1"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sqlite_store.py -v`

Expected: FAIL because models and SQLite store do not exist.

- [ ] **Step 3: Implement shared dataclasses**

Create `src/context_search_tool/models.py` with frozen dataclasses for:

- `SourceFile`
- `SymbolRef`
- `DocumentChunk`
- `RetrievalCandidate`
- `RetrievalResult`

Use `pathlib.Path` for paths and JSON-serializable dictionaries for metadata.

- [ ] **Step 4: Implement SQLite schema and store methods**

Create `src/context_search_tool/sqlite_store.py`.

Schema must include:

- `source_files`
- `chunks`
- `symbols`
- `chunk_symbols`
- `chunk_tokens`
- `chunks_fts` virtual table using FTS5

Required methods:

- `initialize() -> None`
- `upsert_source_file(file: SourceFile) -> None`
- `replace_chunks(file_path: Path, chunks: list[DocumentChunk]) -> None`
- `mark_file_deleted(file_path: Path) -> None`
- `deleted_chunk_ids() -> set[str]`
- `lexical_search(tokens: list[str], limit: int) -> list[RetrievalCandidate]`
- `path_symbol_search(tokens: list[str], limit: int) -> list[RetrievalCandidate]`
- `chunk_for_id(chunk_id: str) -> DocumentChunk`
- `chunk_for_line(file_path: Path, line: int) -> DocumentChunk`
- `active_chunk_ids() -> set[str]`
- `stats() -> dict[str, int]`

Logical deletion must set `deleted_at` on chunks and remove active FTS rows for those chunks.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sqlite_store.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/context_search_tool/models.py src/context_search_tool/sqlite_store.py tests/test_sqlite_store.py
git commit -m "feat: add SQLite metadata and lexical store"
```

---

### Task 5: Generic Chunker And Java Plugin V0

**Files:**
- Create: `src/context_search_tool/plugins.py`
- Create: `src/context_search_tool/chunker.py`
- Create: `src/context_search_tool/java_plugin.py`
- Test: `tests/test_chunker_java_plugin.py`

- [ ] **Step 1: Write failing chunker and Java plugin tests**

Create `tests/test_chunker_java_plugin.py`:

```python
from pathlib import Path

from context_search_tool.chunker import chunk_text
from context_search_tool.java_plugin import JavaPlugin


JAVA_SOURCE = """
package com.example.audit;

import org.apache.ibatis.annotations.Select;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/apply/audit")
public class ApplyAuditController {
    @PostMapping("/pageEs")
    public String pageEs(String applyType) {
        return "ok";
    }
}

enum AuditStatus {
    INVOLVED_BY_ME,
    TOTAL_OVERVIEW
}

interface ApplyAuditMapper {
    @Select("SELECT * FROM audit WHERE status = #{status}")
    String findByStatus(String status);
}
""".strip()


def test_generic_chunker_preserves_line_ranges() -> None:
    chunks = chunk_text(Path("README.md"), "line1\nline2\nline3\n", "markdown", [], max_lines=2)

    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [(1, 2), (3, 3)]
    assert chunks[0].content == "line1\nline2"


def test_java_plugin_extracts_routes_sql_and_enum_values() -> None:
    plugin = JavaPlugin()
    extraction = plugin.extract(Path("ApplyAuditController.java"), JAVA_SOURCE)

    symbol_names = {symbol.name for symbol in extraction.symbols}

    assert "ApplyAuditController" in symbol_names
    assert "pageEs" in symbol_names
    assert "INVOLVED_BY_ME" in symbol_names
    assert "TOTAL_OVERVIEW" in symbol_names
    assert "/apply/audit/pageEs" in extraction.lexical_tokens
    assert "select" in extraction.lexical_tokens
    assert "audit" in extraction.lexical_tokens
    assert "status" in extraction.lexical_tokens
    assert extraction.metadata["package"] == "com.example.audit"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chunker_java_plugin.py -v`

Expected: FAIL because chunker and Java plugin modules do not exist.

- [ ] **Step 3: Implement plugin protocol and generic chunker**

Create `src/context_search_tool/plugins.py` with:

- `PluginExtraction` dataclass containing `symbols`, `lexical_tokens`, and `metadata`.
- `LanguagePlugin` protocol with `supports(path: Path, language: str) -> bool` and `extract(path: Path, content: str) -> PluginExtraction`.
- `default_plugins() -> list[LanguagePlugin]` returning `[JavaPlugin()]`.

Create `src/context_search_tool/chunker.py` with:

- `chunk_text(path: Path, content: str, language: str, plugin_symbols: list[SymbolRef], max_lines: int = 80) -> list[DocumentChunk]`
- `expand_lines(lines: list[str], start_line: int, end_line: int, before: int, after: int) -> tuple[int, int, str]`

`chunk_text` should create deterministic chunk IDs from `path`, line range, and content hash.

- [ ] **Step 4: Implement Java v0 extraction**

Create `src/context_search_tool/java_plugin.py`.

Extraction rules:

- Package: `package\s+([\w.]+)\s*;`
- Imports: `import\s+([\w.*]+)\s*;`
- Class/interface/enum names: `(class|interface|enum)\s+(\w+)`
- Methods: visibility or annotation-adjacent method declarations ending before `{`
- Annotations: `@(\w+)`
- Class-level route: `@RequestMapping("...")` or `@RequestMapping(value = "...")`
- Method routes for `RequestMapping`, `GetMapping`, `PostMapping`, `PutMapping`, `DeleteMapping`, `PatchMapping`
- HTTP method from mapping annotation name or `method = RequestMethod.POST`
- MyBatis SQL annotation text from `@Select`, `@Insert`, `@Update`, `@Delete`
- Enum values inside enum bodies.
- Constants from `static final` field declarations.

Add route path segments, full route paths, SQL words, enum values, constants, package segments, import tail names, class names, method names, and annotation names to lexical tokens.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_chunker_java_plugin.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/context_search_tool/plugins.py src/context_search_tool/chunker.py src/context_search_tool/java_plugin.py tests/test_chunker_java_plugin.py
git commit -m "feat: add generic chunking and Java extraction"
```

---

### Task 6: Embedding Providers And NumPy Vector Store

**Files:**
- Create: `src/context_search_tool/embeddings.py`
- Create: `src/context_search_tool/vector_store.py`
- Test: `tests/test_embeddings_vector_store.py`

- [ ] **Step 1: Write failing embedding and vector store tests**

Create `tests/test_embeddings_vector_store.py`:

```python
from pathlib import Path

import numpy as np

from context_search_tool.config import EmbeddingConfig
from context_search_tool.embeddings import HashEmbeddingProvider, OpenAICompatibleEmbeddingProvider
from context_search_tool.vector_store import NumpyVectorStore


def test_hash_embedding_provider_is_deterministic_and_normalized() -> None:
    provider = HashEmbeddingProvider(EmbeddingConfig(provider="hash", model="hash-v1", dimensions=16))

    first = provider.embed_texts(["apply audit"])[0]
    second = provider.embed_texts(["apply audit"])[0]

    assert np.allclose(first, second)
    assert np.isclose(np.linalg.norm(first), 1.0)
    assert provider.fingerprint()["dimensions"] == 16


def test_openai_compatible_provider_uses_mock_transport() -> None:
    provider = OpenAICompatibleEmbeddingProvider.for_test(
        config=EmbeddingConfig(
            provider="openai-compatible",
            model="demo-embedding",
            dimensions=3,
            base_url="https://example.test/v1",
            api_key_env="CST_TEST_KEY",
        ),
        response_vectors=[[1.0, 0.0, 0.0]],
    )

    vector = provider.embed_texts(["hello"])[0]

    assert vector.tolist() == [1.0, 0.0, 0.0]


def test_numpy_vector_store_persists_and_filters_deleted(tmp_path: Path) -> None:
    store = NumpyVectorStore(tmp_path)
    store.upsert_many(
        [
            ("chunk-a", np.array([1.0, 0.0], dtype=np.float32)),
            ("chunk-b", np.array([0.0, 1.0], dtype=np.float32)),
        ]
    )
    store.persist()

    reloaded = NumpyVectorStore(tmp_path)
    results = reloaded.search(np.array([1.0, 0.0], dtype=np.float32), top_k=2, deleted_ids={"chunk-a"})

    assert [item.chunk_id for item in results] == ["chunk-b"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embeddings_vector_store.py -v`

Expected: FAIL because embedding and vector store modules do not exist.

- [ ] **Step 3: Implement embedding providers**

Create `src/context_search_tool/embeddings.py` with:

- `EmbeddingProvider` protocol.
- `HashEmbeddingProvider`, deterministic and offline.
- `OpenAICompatibleEmbeddingProvider`, using `httpx.Client`.
- `provider_from_config(config: EmbeddingConfig) -> EmbeddingProvider`.

`HashEmbeddingProvider` should hash token bytes into fixed dimensions and L2-normalize vectors. It is the default so tests and local development do not require network credentials. `OpenAICompatibleEmbeddingProvider` should call `POST {base_url}/embeddings` with `{"model": model, "input": texts}` and parse `data[*].embedding`.

- [ ] **Step 4: Implement NumPy vector store**

Create `src/context_search_tool/vector_store.py` with:

- `VectorSearchResult` dataclass containing `chunk_id` and `score`.
- `NumpyVectorStore(index_dir: Path)`.
- `upsert_many(items: list[tuple[str, np.ndarray]]) -> None`.
- `persist() -> None`.
- `search(query_vector: np.ndarray, top_k: int, deleted_ids: set[str]) -> list[VectorSearchResult]`.

Store vectors in `vectors.npy` and IDs in `vector_ids.json`. Normalize vectors before search if needed. Filter deleted chunk IDs before returning results.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_embeddings_vector_store.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/context_search_tool/embeddings.py src/context_search_tool/vector_store.py tests/test_embeddings_vector_store.py
git commit -m "feat: add embedding providers and vector store"
```

---

### Task 7: Manifest Compatibility And Indexing Pipeline

**Files:**
- Create: `src/context_search_tool/manifest.py`
- Create: `src/context_search_tool/indexer.py`
- Test: `tests/test_indexer_manifest.py`

- [ ] **Step 1: Write failing indexer and manifest tests**

Create `tests/test_indexer_manifest.py`:

```python
from pathlib import Path

import pytest

from context_search_tool.config import DEFAULT_CONFIG, EmbeddingConfig, ToolConfig
from context_search_tool.indexer import IncompatibleIndexError, index_repository
from context_search_tool.manifest import load_manifest


def test_index_repository_creates_expected_index_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App { String canApply; }\n", encoding="utf-8")

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_indexed == 1
    assert (repo / ".context-search" / "manifest.json").exists()
    assert (repo / ".context-search" / "index.sqlite").exists()
    assert (repo / ".context-search" / "vectors.npy").exists()
    assert (repo / ".context-search" / "vector_ids.json").exists()
    assert load_manifest(repo).total_chunks >= 1


def test_index_repository_skips_unchanged_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")

    first = index_repository(repo, DEFAULT_CONFIG)
    second = index_repository(repo, DEFAULT_CONFIG)

    assert first.files_indexed == 1
    assert second.files_indexed == 0


def test_index_repository_rejects_incompatible_embedding_config(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)

    incompatible = ToolConfig(
        embedding=EmbeddingConfig(provider="hash", model="hash-v2", dimensions=384)
    )

    with pytest.raises(IncompatibleIndexError):
        index_repository(repo, incompatible)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_indexer_manifest.py -v`

Expected: FAIL because manifest and indexer modules do not exist.

- [ ] **Step 3: Implement manifest handling**

Create `src/context_search_tool/manifest.py` with:

- `Manifest` dataclass.
- `manifest_path(repo: Path) -> Path`.
- `load_manifest(repo: Path) -> Manifest`.
- `write_manifest(repo: Path, manifest: Manifest) -> None`.
- `embedding_config_hash(config: EmbeddingConfig) -> str`.
- `assert_manifest_compatible(repo: Path, config: ToolConfig) -> None`.

Use JSON with sorted keys for stable output.

- [ ] **Step 4: Implement indexing orchestration**

Create `src/context_search_tool/indexer.py` with:

- `IndexSummary` dataclass containing `files_seen`, `files_indexed`, `files_skipped`, `files_deleted`, and `chunks_indexed`.
- `IncompatibleIndexError`.
- `index_repository(repo: Path, config: ToolConfig) -> IndexSummary`.

Index flow:

1. Ensure `.context-search/`.
2. Load or write config.
3. Check manifest compatibility when manifest exists.
4. Initialize SQLite.
5. Scan workspace.
6. Mark removed previously indexed files deleted.
7. For each changed file, read text, run plugin extraction, chunk text, upsert source file and chunks.
8. Embed changed chunks.
9. Upsert vectors and persist.
10. Write manifest stats.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_indexer_manifest.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/context_search_tool/manifest.py src/context_search_tool/indexer.py tests/test_indexer_manifest.py
git commit -m "feat: index repositories with manifest checks"
```

---

### Task 8: Retrieval Pipeline, Reranking, And Context Expansion

**Files:**
- Create: `src/context_search_tool/retrieval.py`
- Test: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Write failing retrieval tests**

Create `tests/test_retrieval_pipeline.py`:

```python
from pathlib import Path

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_retrieval_pipeline.py -v`

Expected: FAIL because `retrieval.py` does not exist.

- [ ] **Step 3: Implement retrieval dataclasses and query pipeline**

Create `src/context_search_tool/retrieval.py` with:

- `QueryBundle` dataclass containing `query`, `expanded_tokens`, `results`, and `followup_keywords`.
- `query_repository(repo: Path, query: str, config: ToolConfig, context_lines: int | None = None, full_file: bool = False) -> QueryBundle`.

Pipeline:

1. Tokenize query.
2. Search vector store with embedded query.
3. Search SQLite lexical FTS.
4. Search SQLite path/symbol tables.
5. Merge candidates by chunk ID.
6. Score using semantic score, lexical score, path/symbol score, exact token coverage, Java plugin boosts, generated/test penalties.
7. Load chunks.
8. Expand context lines and merge overlapping ranges from the same file.
9. Enforce `max_full_file_bytes` when `full_file=True`.
10. Return top `config.retrieval.final_top_k`.

Each `RetrievalResult.score_parts` must include keys for available sources, such as `semantic`, `lexical`, `path_symbol`, `token_coverage`, and `plugin_boost`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_retrieval_pipeline.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "feat: retrieve and rerank context bundles"
```

---

### Task 9: Markdown And JSON Formatters

**Files:**
- Create: `src/context_search_tool/formatters.py`
- Test: `tests/test_formatters.py`

- [ ] **Step 1: Write failing formatter tests**

Create `tests/test_formatters.py`:

```python
import json
from pathlib import Path

from context_search_tool.models import RetrievalResult
from context_search_tool.retrieval import QueryBundle
from context_search_tool.formatters import format_json, format_markdown


def sample_bundle() -> QueryBundle:
    return QueryBundle(
        query="apply audit",
        expanded_tokens=["apply", "audit"],
        followup_keywords=["pageEs", "INVOLVED_BY_ME"],
        results=[
            RetrievalResult(
                file_path=Path("ApplyAuditController.java"),
                start_line=10,
                end_line=20,
                content="class ApplyAuditController {}",
                score=0.87,
                score_parts={"lexical": 0.8},
                reasons=["lexical match: apply audit"],
                followup_keywords=["pageEs"],
            )
        ],
    )


def test_markdown_formatter_contains_paths_reasons_and_snippets() -> None:
    output = format_markdown(sample_bundle())

    assert "ApplyAuditController.java:10-20" in output
    assert "lexical match: apply audit" in output
    assert "```" in output


def test_json_formatter_is_structured() -> None:
    output = format_json(sample_bundle())
    parsed = json.loads(output)

    assert parsed["query"] == "apply audit"
    assert parsed["results"][0]["file_path"] == "ApplyAuditController.java"
    assert parsed["results"][0]["score_parts"]["lexical"] == 0.8
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_formatters.py -v`

Expected: FAIL because `formatters.py` does not exist.

- [ ] **Step 3: Implement Markdown and JSON formatters**

Create `src/context_search_tool/formatters.py` with:

- `format_markdown(bundle: QueryBundle) -> str`
- `format_json(bundle: QueryBundle) -> str`

Markdown sections:

1. `# Context Search Results`
2. Query and expanded tokens.
3. Numbered result sections with path, line range, score, reasons, score parts, snippet.
4. Follow-up keywords.

JSON must serialize paths as POSIX strings and include all result fields.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_formatters.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/formatters.py tests/test_formatters.py
git commit -m "feat: format retrieval bundles"
```

---

### Task 10: CLI Commands

**Files:**
- Modify: `src/context_search_tool/cli.py`
- Test: `tests/test_cli_commands.py`

- [ ] **Step 1: Write failing CLI command tests**

Create `tests/test_cli_commands.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from context_search_tool.cli import app


def test_cli_index_query_stats_explain_and_clean(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "ApplyAuditController.java"
    source.write_text(
        '''
import org.springframework.web.bind.annotation.PostMapping;

class ApplyAuditController {
  @PostMapping("/apply/audit/pageEs")
  String pageEs() { return "ok"; }
}
'''.strip(),
        encoding="utf-8",
    )
    runner = CliRunner()

    index_result = runner.invoke(app, ["index", str(repo)])
    assert index_result.exit_code == 0
    assert "indexed" in index_result.output.lower()

    query_result = runner.invoke(app, ["query", str(repo), "/apply/audit/pageEs", "--json"])
    assert query_result.exit_code == 0
    parsed = json.loads(query_result.output)
    assert parsed["results"]

    stats_result = runner.invoke(app, ["stats", str(repo)])
    assert stats_result.exit_code == 0
    assert "Total chunks" in stats_result.output

    explain_result = runner.invoke(app, ["explain", str(repo), "ApplyAuditController.java:4"])
    assert explain_result.exit_code == 0
    assert "ApplyAuditController.java" in explain_result.output

    monkeypatch.chdir(repo)
    cwd_query_result = runner.invoke(app, ["query", "/apply/audit/pageEs"])
    assert cwd_query_result.exit_code == 0
    assert "ApplyAuditController.java" in cwd_query_result.output

    clean_result = runner.invoke(app, ["clean", str(repo)])
    assert clean_result.exit_code == 0
    assert not (repo / ".context-search").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_commands.py -v`

Expected: FAIL because CLI commands are not implemented.

- [ ] **Step 3: Implement CLI commands**

Modify `src/context_search_tool/cli.py` to define:

- `index(repo: Path | None = None)`
- `query(repo_or_question: str, question: str | None = None, json_output: bool = False, context_lines: int | None = None, full_file: bool = False)`
- `status(repo: Path | None = None)`
- `stats(repo: Path | None = None)`
- `explain(repo: Path | None, location: str)`
- `clean(repo: Path | None = None)`

Command behavior:

- Query supports both `cst query <repo> "<question>"` and `cst query "<question>"`.
- Use `find_repo_root` for omitted repository paths.
- `status` reports whether index files exist.
- `stats` prints files, chunks, deleted chunks, embedding config, and disk usage.
- `explain` parses `file:line`, finds the covering chunk, and prints chunk ID, type, line range, symbols, lexical tokens, embedding ID, and metadata.
- `clean` removes `.context-search/` after resolving the repository.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli_commands.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/cli.py tests/test_cli_commands.py
git commit -m "feat: expose indexing and query CLI commands"
```

---

### Task 11: Java Fixture Acceptance Coverage

**Files:**
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditController.java`
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/EsApplyAuditPageQryExe.java`
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditMapper.java`
- Create: `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/AuditStatus.java`
- Test: `tests/test_acceptance_java_fixture.py`

- [ ] **Step 1: Create fixture repository files**

Create `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditController.java`:

```java
package com.example.audit;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/apply/audit")
public class ApplyAuditController {
    @PostMapping("/pageEs")
    public String pageEs(EsApplyAuditPageQryExe query) {
        return query.execute(AuditStatus.INVOLVED_BY_ME);
    }
}
```

Create `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/EsApplyAuditPageQryExe.java`:

```java
package com.example.audit;

public class EsApplyAuditPageQryExe {
    private final ApplyAuditMapper mapper = null;

    public String execute(AuditStatus auditStatus) {
        return mapper.findByStatus(auditStatus.name());
    }
}
```

Create `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditMapper.java`:

```java
package com.example.audit;

import org.apache.ibatis.annotations.Select;

public interface ApplyAuditMapper {
    @Select("SELECT * FROM apply_audit WHERE status = #{status}")
    String findByStatus(String status);
}
```

Create `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/AuditStatus.java`:

```java
package com.example.audit;

public enum AuditStatus {
    INVOLVED_BY_ME,
    TOTAL_OVERVIEW
}
```

- [ ] **Step 2: Write failing acceptance test**

Create `tests/test_acceptance_java_fixture.py`:

```python
import shutil
from pathlib import Path

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository


def test_java_fixture_surfaces_controller_query_mapper_and_enum(tmp_path: Path) -> None:
    source_fixture = Path("tests/fixtures/java-spring-mini")
    repo = tmp_path / "java-spring-mini"
    shutil.copytree(source_fixture, repo)

    index_repository(repo, DEFAULT_CONFIG)
    bundle = query_repository(
        repo,
        "/apply/audit/pageEs INVOLVED_BY_ME why does it leak across regions",
        DEFAULT_CONFIG,
        context_lines=20,
    )

    paths = {result.file_path.name for result in bundle.results}

    assert "ApplyAuditController.java" in paths
    assert "AuditStatus.java" in paths
    assert "ApplyAuditMapper.java" in paths
    assert bundle.results[0].score > 0
```

- [ ] **Step 3: Run test to verify current behavior**

Run: `pytest tests/test_acceptance_java_fixture.py -v`

Expected: PASS if previous tasks already satisfy acceptance. If it fails, inspect score reasons and adjust only the smallest relevant ranking rule or Java token extraction rule.

- [ ] **Step 4: Run focused integration tests**

Run: `pytest tests/test_acceptance_java_fixture.py tests/test_retrieval_pipeline.py tests/test_cli_commands.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/java-spring-mini tests/test_acceptance_java_fixture.py
git commit -m "test: add Java retrieval acceptance fixture"
```

---

### Task 12: Documentation And Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README usage**

Modify `README.md` to include:

````markdown
# Context Search Tool

Local hybrid semantic retrieval for codebases.

## Install For Development

```bash
python -m pip install -e ".[dev]"
```

## Basic Usage

```bash
cst index /path/to/repo
cst query /path/to/repo "/apply/audit/pageEs INVOLVED_BY_ME"
cd /path/to/repo
cst query "/apply/audit/pageEs INVOLVED_BY_ME" --context-lines 20
cst query /path/to/repo "canApply filter" --json
cst stats /path/to/repo
cst explain /path/to/repo src/main/java/App.java:42
```

Indexes are stored in the target repository under `.context-search/`.

## Embeddings

The default `hash` provider is deterministic and offline. It is useful for development, tests, and exact-token-heavy searches. Configure `openai-compatible` in `.context-search/config.toml` to use a real embedding service that exposes `/v1/embeddings`.
````

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 3: Run CLI smoke test on fixture**

Run:

```bash
python -m context_search_tool.cli index tests/fixtures/java-spring-mini
python -m context_search_tool.cli query tests/fixtures/java-spring-mini "/apply/audit/pageEs INVOLVED_BY_ME" --json
python -m context_search_tool.cli stats tests/fixtures/java-spring-mini
python -m context_search_tool.cli explain tests/fixtures/java-spring-mini src/main/java/com/example/audit/ApplyAuditController.java:9
```

Expected:

- Index command reports indexed files and chunks.
- Query JSON contains non-empty `results`.
- Stats output contains `Total chunks`.
- Explain output names `ApplyAuditController.java`.

- [ ] **Step 4: Clean fixture index created by smoke test**

Run:

```bash
python -m context_search_tool.cli clean tests/fixtures/java-spring-mini
```

Expected: `tests/fixtures/java-spring-mini/.context-search/` no longer exists.

- [ ] **Step 5: Check git status**

Run: `git status --short`

Expected: only intended source, test, and README changes are present.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: document context search CLI usage"
```

---

## Self-Review Against Spec

Spec coverage:

- CLI commands: Tasks 1, 10, and 12.
- Per-repo `.context-search/`: Tasks 2 and 7.
- Manifest and embedding compatibility: Tasks 6 and 7.
- Scanner and ignore handling: Task 3.
- Generic chunking: Task 5.
- Java plugin v0: Tasks 5 and 11.
- SQLite FTS and metadata store: Task 4.
- NumPy vector store: Task 6.
- Hybrid retrieval, rerank, and context expansion: Task 8.
- Markdown and JSON output: Task 9.
- `stats` and `explain`: Task 10.
- Acceptance fixture: Task 11.

Deferred by spec and not implemented by this plan:

- MCP server.
- Interactive query mode.
- Additional output formats.
- Config management commands.
- Compact and forced reindex commands.
- Tree-sitter or JDT parsing.
- MyBatis XML relationship extraction.
- Lombok virtual method indexing.
- Validation annotation-specific ranking.
- Call graph and reference graph reranking.
- Commit history indexing.
- LLM or cross-encoder reranker.
- Agentic Fast Context-style retrieval stage.
- Remote or multi-user service.
