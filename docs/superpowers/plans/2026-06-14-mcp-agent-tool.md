# MCP Agent Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose Context Search Tool as a local MCP server that coding agents can call, and record real MCP query feedback before changing the default embedding model.

**Architecture:** Add a thin MCP layer around the existing core API instead of shelling out to the CLI. Keep retrieval, indexing, stats, and explain behavior in reusable tool functions, register those functions with FastMCP over stdio, and append minimal JSONL call feedback under the target repository's existing `.context-search/` directory. Keep `hash-v1` as the default embedding provider for this milestone; use the MCP feedback log to decide whether a stronger embedding provider is needed.

**Tech Stack:** Python 3.11+, official `mcp` Python SDK v1.x, FastMCP, Typer, SQLite FTS5, NumPy, pytest, existing Java fixture tests.

---

## Context

The repository already has the pieces an MCP server should wrap:

- `src/context_search_tool/cli.py` resolves repositories and calls `query_repository()`.
- `src/context_search_tool/retrieval.py` returns a structured `QueryBundle`.
- `src/context_search_tool/formatters.py` already emits structured JSON with summary, results, score parts, reasons, and follow-up keywords.
- `src/context_search_tool/embeddings.py` already has a provider boundary with `hash` and `openai-compatible`.
- The README names "MCP server or agent tool interface" as a next-stage direction.

The next milestone is therefore an agent-facing contract and feedback loop, not a retrieval rewrite.

## Assumptions

- Use the official Python MCP SDK and pin it to v1.x with `mcp[cli]>=1.27,<2` because the upstream README describes v1.x as stable and v2 as alpha.
- Verify `from mcp.server.fastmcp import FastMCP` immediately after dependency installation. The current local environment does not have `mcp` installed, so the implementation must not treat the import path as locally verified before Task 1 runs.
- Use stdio transport first because local coding agents commonly launch MCP servers as subprocesses.
- Do not print to stdout from the MCP server path; stdout is reserved for JSON-RPC messages in stdio transport. Configure MCP server logging to a file before calling `mcp.run(transport="stdio")`.
- Keep `cst` CLI behavior unchanged.
- Do not expose `clean` as an MCP tool in this milestone because it deletes repository-local index state.
- Do not change the default embedding provider in this milestone.
- Do not log source snippets or full file content in the MCP feedback log.
- Rotate `mcp_calls.jsonl` when it exceeds 10 MiB so long-running agent usage does not grow one unbounded file forever.
- Preserve the existing `[project.optional-dependencies] dev = ["pytest>=8.0.0"]` block in `pyproject.toml`.
- If a query is attempted before indexing, return a structured `missing_index` error and do not create `.context-search/`.

## Scope

In scope:

- MCP dependency and console entry point.
- Pure Python MCP tool functions for index, query, stats, and explain.
- FastMCP stdio server registration.
- Structured success and error payloads that agents can consume without parsing CLI text.
- Minimal MCP call feedback JSONL for query calls.
- Tests for tool functions, no-index behavior, feedback logging, and server import.
- README instructions for local agent configuration and embedding feedback workflow.

Out of scope:

- HTTP transport.
- Authentication.
- Remote service deployment.
- Resource or prompt primitives.
- Deleting indexes from MCP.
- Real semantic model selection or default embedding change.
- Cross-encoder or LLM reranking.

## File Map

- Modify `pyproject.toml`
  - Add `mcp[cli]>=1.27,<2` to dependencies.
  - Add `cst-mcp = "context_search_tool.mcp_server:main"` to project scripts.
- Create `src/context_search_tool/mcp_tools.py`
  - Define pure Python tool functions that return structured dictionaries.
  - Add helper functions for config loading, index checks, query payload conversion, stats, explain, and feedback logging.
- Create `src/context_search_tool/mcp_server.py`
  - Register MCP tools with FastMCP.
  - Run stdio transport in `main()`.
- Add `tests/test_mcp_tools.py`
  - Cover index, query, stats, explain, missing index, top-k override, and feedback logging.
- Add `tests/test_mcp_server.py`
  - Cover importability and server object creation.
- Modify `README.md`
  - Document `cst-mcp`, tool list, local MCP config shape, feedback log, and embedding decision gate.

---

### Task 1: Add MCP Dependency And Entry Point

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing import test**

Create `tests/test_mcp_server.py`:

```python
def test_mcp_server_imports() -> None:
    from context_search_tool import mcp_server

    assert mcp_server.SERVER_NAME == "context-search-tool"
    assert mcp_server.mcp is not None
    assert callable(mcp_server.main)
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
pytest tests/test_mcp_server.py -v
```

Expected: FAIL with `ImportError: cannot import name 'mcp_server'`.

- [ ] **Step 3: Add MCP dependency and console script**

Modify `pyproject.toml`:

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
  "httpx>=0.27.0",
  "mcp[cli]>=1.27,<2"
]

[project.scripts]
cst = "context_search_tool.cli:app"
cst-mcp = "context_search_tool.mcp_server:main"

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0"
]
```

Keep the existing `[project.optional-dependencies]` block. Do not replace `pytest>=8.0.0` with an older lower bound.

- [ ] **Step 4: Add a minimal MCP server module**

Create `src/context_search_tool/mcp_server.py`:

```python
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

SERVER_NAME = "context-search-tool"

mcp = FastMCP(SERVER_NAME)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Install dependencies for the local environment**

Run:

```bash
python3 -m pip install -e ".[dev]"
```

Expected: package installs with `mcp` available.

- [ ] **Step 6: Verify the MCP SDK import and constructor**

Run:

```bash
python3 -c "from mcp.server.fastmcp import FastMCP; import inspect; print(FastMCP); print(inspect.signature(FastMCP))"
```

Expected: import succeeds and prints the `FastMCP` class plus constructor signature. If this fails, inspect the installed `mcp` package and adjust only `src/context_search_tool/mcp_server.py` and this plan's import examples to match the installed SDK.

- [ ] **Step 7: Verify the server import test**

Run:

```bash
pytest tests/test_mcp_server.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add pyproject.toml src/context_search_tool/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add mcp server entry point"
```

---

### Task 2: Add Pure MCP Tool Functions

**Files:**
- Create: `src/context_search_tool/mcp_tools.py`
- Test: `tests/test_mcp_tools.py`

- [ ] **Step 1: Write failing tests for index, query, stats, and explain**

Create `tests/test_mcp_tools.py`:

```python
import json
from pathlib import Path

import context_search_tool.mcp_tools as mcp_tools
from context_search_tool.mcp_tools import (
    context_search_explain_tool,
    context_search_index_tool,
    context_search_query_tool,
    context_search_stats_tool,
)


def _write_java_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "ApplyAuditController.java").write_text(
        '''
import org.springframework.web.bind.annotation.PostMapping;

class ApplyAuditController {
  @PostMapping("/apply/audit/pageEs")
  String pageEs() { return service.pageEs(); }
}
'''.strip(),
        encoding="utf-8",
    )
    (repo / "ApplyAuditServiceImpl.java").write_text(
        '''
class ApplyAuditServiceImpl {
  String pageEs() { return "ok"; }
}
'''.strip(),
        encoding="utf-8",
    )


def test_mcp_tools_index_query_stats_and_explain(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)

    indexed = context_search_index_tool(str(repo))
    assert indexed["ok"] is True
    assert indexed["summary"]["files_indexed"] == 2
    assert indexed["summary"]["chunks_indexed"] >= 2

    queried = context_search_query_tool(
        repo=str(repo),
        query="/apply/audit/pageEs",
        context_lines=0,
        full_file=False,
        final_top_k=1,
    )
    assert queried["ok"] is True
    assert queried["query"] == "/apply/audit/pageEs"
    assert len(queried["results"]) == 1
    assert queried["results"][0]["file_path"] == "ApplyAuditController.java"
    assert "content" in queried["results"][0]
    assert queried["summary"]["entry_points"]

    stats = context_search_stats_tool(str(repo))
    assert stats["ok"] is True
    assert stats["stats"]["total_files"] == 2
    assert stats["embedding"]["provider"] == "hash"

    explained = context_search_explain_tool(str(repo), "ApplyAuditController.java:4")
    assert explained["ok"] is True
    assert explained["chunk"]["file_path"] == "ApplyAuditController.java"
    assert explained["chunk"]["start_line"] <= 4 <= explained["chunk"]["end_line"]


def test_mcp_query_missing_index_does_not_create_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = context_search_query_tool(str(repo), "anything")

    assert result == {
        "ok": False,
        "error": {
            "code": "missing_index",
            "message": f"Missing index for {repo}. Run context_search_index first.",
        },
    }
    assert not (repo / ".context-search").exists()


def test_mcp_query_writes_feedback_without_source_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_query_tool(str(repo), "/apply/audit/pageEs")

    assert result["ok"] is True
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    event = events[0]
    assert event["tool"] == "context_search_query"
    assert event["ok"] is True
    assert event["query"] == "/apply/audit/pageEs"
    assert event["result_count"] >= 1
    assert event["embedding"]["provider"] == "hash"
    assert "ApplyAuditController" not in json.dumps(event)
    assert "class ApplyAuditController" not in json.dumps(event)


def test_mcp_query_rotates_large_feedback_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    log_path.write_text("oversized\n", encoding="utf-8")
    monkeypatch.setattr(mcp_tools, "_FEEDBACK_LOG_MAX_BYTES", 1)

    result = context_search_query_tool(str(repo), "/apply/audit/pageEs")

    assert result["ok"] is True
    rotated = sorted(log_path.parent.glob("mcp_calls.*.jsonl"))
    assert len(rotated) == 1
    assert rotated[0].read_text(encoding="utf-8") == "oversized\n"
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 1
```

- [ ] **Step 2: Run the focused failing tests**

Run:

```bash
pytest tests/test_mcp_tools.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'context_search_tool.mcp_tools'`.

- [ ] **Step 3: Implement pure tool functions**

Create `src/context_search_tool/mcp_tools.py`:

```python
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx

from context_search_tool.config import ToolConfig, load_config
from context_search_tool.indexer import (
    IncompatibleIndexError,
    index_repository,
    signal_schema_is_current,
)
from context_search_tool.manifest import load_manifest
from context_search_tool.models import DocumentChunk, RetrievalResult, SymbolRef
from context_search_tool.paths import (
    RepositoryNotFoundError,
    find_repo_root,
    index_dir_for,
)
from context_search_tool.retrieval import QueryBundle, query_repository
from context_search_tool.sqlite_store import SQLiteStore

_FEEDBACK_LOG_MAX_BYTES = 10 * 1024 * 1024


def context_search_index_tool(repo: str) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
        config = load_config(resolved_repo)
        summary = index_repository(resolved_repo, config)
    except (RepositoryNotFoundError, IncompatibleIndexError, ValueError, httpx.HTTPError) as exc:
        return _error("index_failed", str(exc))

    return {
        "ok": True,
        "repo": str(resolved_repo),
        "summary": {
            "files_seen": summary.files_seen,
            "files_indexed": summary.files_indexed,
            "files_skipped": summary.files_skipped,
            "files_deleted": summary.files_deleted,
            "chunks_indexed": summary.chunks_indexed,
        },
    }


def context_search_query_tool(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    index_dir = index_dir_for(resolved_repo)
    if not (index_dir / "index.sqlite").exists():
        return _error(
            "missing_index",
            f"Missing index for {resolved_repo}. Run context_search_index first.",
        )

    try:
        config = _load_query_config(resolved_repo, final_top_k)
        bundle = query_repository(
            resolved_repo,
            query,
            config,
            context_lines=context_lines,
            full_file=full_file,
        )
        payload = _query_payload(bundle)
        payload["ok"] = True
        payload["repo"] = str(resolved_repo)
        payload["index"] = _index_state(resolved_repo, config)
        _append_query_feedback(
            resolved_repo,
            query=query,
            payload=payload,
            context_lines=context_lines,
            full_file=full_file,
            final_top_k=final_top_k,
        )
        return payload
    except (ValueError, httpx.HTTPError) as exc:
        _append_query_feedback(
            resolved_repo,
            query=query,
            payload=_error("query_failed", str(exc)),
            context_lines=context_lines,
            full_file=full_file,
            final_top_k=final_top_k,
        )
        return _error("query_failed", str(exc))


def context_search_stats_tool(repo: str) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    index_dir = index_dir_for(resolved_repo)
    if not (index_dir / "index.sqlite").exists():
        return _error(
            "missing_index",
            f"Missing index for {resolved_repo}. Run context_search_index first.",
        )

    config = load_config(resolved_repo)
    store = SQLiteStore(index_dir / "index.sqlite")
    counts = store.stats()
    manifest = load_manifest(resolved_repo) if (index_dir / "manifest.json").exists() else None
    provider = manifest.embedding_provider if manifest is not None else config.embedding.provider
    model = manifest.embedding_model if manifest is not None else config.embedding.model
    dimensions = (
        manifest.embedding_dimensions if manifest is not None else config.embedding.dimensions
    )
    return {
        "ok": True,
        "repo": str(resolved_repo),
        "stats": {
            "total_files": counts["source_files"],
            "total_chunks": counts["active_chunks"],
            "deleted_chunks": counts["deleted_chunks"],
            "symbols": counts["symbols"],
            "lexical_tokens": counts["tokens"],
            "disk_usage_bytes": _disk_usage(index_dir),
        },
        "embedding": {
            "provider": provider,
            "model": model,
            "dimensions": dimensions,
        },
    }


def context_search_explain_tool(repo: str, location: str) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    try:
        file_path, line = _parse_location(location, resolved_repo)
    except ValueError as exc:
        return _error("invalid_location", str(exc))

    index_dir = index_dir_for(resolved_repo)
    if not (index_dir / "index.sqlite").exists():
        return _error(
            "missing_index",
            f"Missing index for {resolved_repo}. Run context_search_index first.",
        )

    store = SQLiteStore(index_dir / "index.sqlite")
    try:
        chunk = store.chunk_for_line(file_path, line)
    except KeyError:
        return _error(
            "chunk_not_found",
            f"No indexed chunk covers {file_path.as_posix()}:{line}.",
        )

    return {
        "ok": True,
        "repo": str(resolved_repo),
        "chunk": _chunk_payload(chunk),
    }


def _load_query_config(repo: Path, final_top_k: int | None) -> ToolConfig:
    config = load_config(repo)
    if final_top_k is None:
        return config
    if final_top_k < 1:
        raise ValueError("final_top_k must be greater than zero")
    return replace(
        config,
        retrieval=replace(config.retrieval, final_top_k=final_top_k),
    )


def _query_payload(bundle: QueryBundle) -> dict[str, Any]:
    return {
        "query": bundle.query,
        "expanded_tokens": bundle.expanded_tokens,
        "followup_keywords": bundle.followup_keywords,
        "summary": {
            "entry_points": bundle.summary.entry_points,
            "implementation": bundle.summary.implementation,
            "related_types": bundle.summary.related_types,
            "possibly_legacy": bundle.summary.possibly_legacy,
        },
        "results": [_result_payload(result) for result in bundle.results],
    }


def _result_payload(result: RetrievalResult) -> dict[str, Any]:
    return {
        "file_path": result.file_path.as_posix(),
        "start_line": result.start_line,
        "end_line": result.end_line,
        "content": result.content,
        "score": result.score,
        "score_parts": result.score_parts,
        "reasons": result.reasons,
        "followup_keywords": result.followup_keywords,
    }


def _chunk_payload(chunk: DocumentChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "file_path": chunk.file_path.as_posix(),
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "chunk_type": chunk.chunk_type,
        "symbols": [_symbol_payload(symbol) for symbol in chunk.symbols],
        "lexical_tokens": chunk.lexical_tokens,
        "embedding_id": chunk.embedding_id,
        "metadata": chunk.metadata,
    }


def _symbol_payload(symbol: SymbolRef) -> dict[str, Any]:
    return {
        "name": symbol.name,
        "kind": symbol.kind,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "language": symbol.language,
        "metadata": symbol.metadata,
    }


def _index_state(repo: Path, config: ToolConfig) -> dict[str, Any]:
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")
    store.initialize()
    return {
        "signal_schema_current": signal_schema_is_current(store),
        "embedding": {
            "provider": config.embedding.provider,
            "model": config.embedding.model,
            "dimensions": config.embedding.dimensions,
        },
    }


def _append_query_feedback(
    repo: Path,
    query: str,
    payload: dict[str, Any],
    context_lines: int | None,
    full_file: bool,
    final_top_k: int | None,
) -> None:
    index_dir = index_dir_for(repo)
    if not index_dir.exists():
        return
    event = {
        "timestamp": int(time.time()),
        "tool": "context_search_query",
        "ok": bool(payload.get("ok")),
        "repo_hash": _short_hash(str(repo)),
        "query": query,
        "context_lines": context_lines,
        "full_file": full_file,
        "final_top_k": final_top_k,
        "result_count": len(payload.get("results", [])),
        "top_score": _top_score(payload),
        "top_score_parts": _top_score_parts(payload),
        "summary_counts": _summary_counts(payload),
        "followup_keyword_count": len(payload.get("followup_keywords", [])),
        "embedding": payload.get("index", {}).get("embedding", {}),
        "error_code": payload.get("error", {}).get("code"),
    }
    log_path = index_dir / "mcp_calls.jsonl"
    _rotate_feedback_log(log_path)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")


def _rotate_feedback_log(log_path: Path) -> None:
    if not log_path.exists() or log_path.stat().st_size <= _FEEDBACK_LOG_MAX_BYTES:
        return
    rotated_path = log_path.with_name(f"mcp_calls.{time.time_ns()}.jsonl")
    log_path.replace(rotated_path)


def _top_score(payload: dict[str, Any]) -> float | None:
    results = payload.get("results", [])
    if not results:
        return None
    return results[0].get("score")


def _top_score_parts(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results", [])
    if not results:
        return {}
    return dict(results[0].get("score_parts", {}))


def _summary_counts(payload: dict[str, Any]) -> dict[str, int]:
    summary = payload.get("summary", {})
    return {
        "entry_points": len(summary.get("entry_points", [])),
        "implementation": len(summary.get("implementation", [])),
        "related_types": len(summary.get("related_types", [])),
        "possibly_legacy": len(summary.get("possibly_legacy", [])),
    }


def _parse_location(location: str, repo: Path) -> tuple[Path, int]:
    if ":" not in location:
        raise ValueError("location must be file:line")
    raw_path, raw_line = location.rsplit(":", 1)
    try:
        line = int(raw_line)
    except ValueError as exc:
        raise ValueError("line must be an integer") from exc
    if line < 1:
        raise ValueError("line must be greater than zero")

    path = Path(raw_path)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(repo)
        except ValueError:
            raise ValueError("absolute path must be inside repo")
    return path, line


def _disk_usage(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _error(code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
```

- [ ] **Step 4: Verify the focused tests**

Run:

```bash
pytest tests/test_mcp_tools.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/context_search_tool/mcp_tools.py tests/test_mcp_tools.py
git commit -m "feat: add mcp tool functions"
```

---

### Task 3: Register MCP Tools With FastMCP

**Files:**
- Modify: `src/context_search_tool/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Extend the server import test**

Replace `tests/test_mcp_server.py` with:

```python
def test_mcp_server_imports() -> None:
    from context_search_tool import mcp_server

    assert mcp_server.SERVER_NAME == "context-search-tool"
    assert mcp_server.mcp is not None
    assert callable(mcp_server.main)
    assert callable(mcp_server.context_search_index)
    assert callable(mcp_server.context_search_query)
    assert callable(mcp_server.context_search_stats)
    assert callable(mcp_server.context_search_explain)
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
pytest tests/test_mcp_server.py -v
```

Expected: FAIL because registered wrapper functions are not defined yet.

- [ ] **Step 3: Register the MCP tools**

Replace `src/context_search_tool/mcp_server.py` with:

```python
from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from context_search_tool.mcp_tools import (
    context_search_explain_tool,
    context_search_index_tool,
    context_search_query_tool,
    context_search_stats_tool,
)

SERVER_NAME = "context-search-tool"
DEFAULT_LOG_FILE = "/tmp/cst-mcp.log"

mcp = FastMCP(SERVER_NAME)


@mcp.tool()
def context_search_index(repo: str) -> dict[str, Any]:
    """Create or update the Context Search index for a local repository."""
    return context_search_index_tool(repo)


@mcp.tool()
def context_search_query(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
) -> dict[str, Any]:
    """Search indexed code context in a local repository."""
    return context_search_query_tool(
        repo=repo,
        query=query,
        context_lines=context_lines,
        full_file=full_file,
        final_top_k=final_top_k,
    )


@mcp.tool()
def context_search_stats(repo: str) -> dict[str, Any]:
    """Return index and embedding statistics for a local repository."""
    return context_search_stats_tool(repo)


@mcp.tool()
def context_search_explain(repo: str, location: str) -> dict[str, Any]:
    """Explain which indexed chunk covers a file:line location."""
    return context_search_explain_tool(repo, location)


def main() -> None:
    logging.basicConfig(
        filename=os.environ.get("CST_MCP_LOG_FILE", DEFAULT_LOG_FILE),
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify server and tool tests**

Run:

```bash
pytest tests/test_mcp_server.py tests/test_mcp_tools.py -v
```

Expected: PASS.

- [ ] **Step 5: Verify the console script resolves**

Run:

```bash
python3 -c "from importlib.metadata import entry_points; print([ep.name for ep in entry_points(group='console_scripts') if ep.name in {'cst', 'cst-mcp'}])"
```

Expected output contains both `cst` and `cst-mcp`.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/context_search_tool/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: register context search mcp tools"
```

---

### Task 4: Harden MCP Tool Contract Around Error Cases

**Files:**
- Modify: `tests/test_mcp_tools.py`
- Modify: `src/context_search_tool/mcp_tools.py`

- [ ] **Step 1: Add tests for invalid input and incompatible top-k**

Append to `tests/test_mcp_tools.py`:

```python
def test_mcp_query_rejects_invalid_final_top_k(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_query_tool(str(repo), "audit", final_top_k=0)

    assert result == {
        "ok": False,
        "error": {
            "code": "query_failed",
            "message": "final_top_k must be greater than zero",
        },
    }


def test_mcp_explain_rejects_invalid_location(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_explain_tool(str(repo), "ApplyAuditController.java")

    assert result == {
        "ok": False,
        "error": {
            "code": "invalid_location",
            "message": "location must be file:line",
        },
    }


def test_mcp_explain_reports_missing_chunk(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_explain_tool(str(repo), "Missing.java:99")

    assert result == {
        "ok": False,
        "error": {
            "code": "chunk_not_found",
            "message": "No indexed chunk covers Missing.java:99.",
        },
    }


def test_mcp_explain_rejects_absolute_path_outside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    other = tmp_path / "other"
    _write_java_repo(repo)
    other.mkdir()
    outside_file = other / "Outside.java"
    outside_file.write_text("class Outside {}\n", encoding="utf-8")
    context_search_index_tool(str(repo))

    result = context_search_explain_tool(str(repo), f"{outside_file}:1")

    assert result == {
        "ok": False,
        "error": {
            "code": "invalid_location",
            "message": "absolute path must be inside repo",
        },
    }
```

- [ ] **Step 2: Run the focused tests**

Run:

```bash
pytest tests/test_mcp_tools.py -v
```

Expected: PASS if Task 2 implementation already returns these errors. If a test fails, adjust only `mcp_tools.py` so the returned error dictionaries match these expected payloads.

- [ ] **Step 3: Verify query feedback still logs failed query calls without snippets**

Run:

```bash
pytest tests/test_mcp_tools.py::test_mcp_query_rejects_invalid_final_top_k tests/test_mcp_tools.py::test_mcp_query_writes_feedback_without_source_content -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add src/context_search_tool/mcp_tools.py tests/test_mcp_tools.py
git commit -m "test: cover mcp tool error contract"
```

---

### Task 5: Document Agent Usage And Feedback Loop

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add README MCP section**

Insert this section after the `CLI 命令` section and before `配置`:

````markdown
## MCP Server

`cst-mcp` starts a local stdio MCP server for coding agents. The server wraps the same core API as the CLI; it does not shell out to `cst`.

Available tools:

- `context_search_index(repo)` creates or updates `.context-search/`.
- `context_search_query(repo, query, context_lines, full_file, final_top_k)` returns summary, ranked results, score parts, reasons, and follow-up keywords.
- `context_search_stats(repo)` returns index counts and embedding configuration.
- `context_search_explain(repo, location)` explains the chunk covering a `file:line` location.

The MCP server intentionally does not expose `clean`, because deleting index state is too destructive for an agent-facing default tool.

Example local MCP config:

```json
{
  "mcpServers": {
    "context-search-tool": {
      "command": "cst-mcp",
      "args": []
    }
  }
}
```

If the package is not installed globally, use the module entry point from this repository:

```json
{
  "mcpServers": {
    "context-search-tool": {
      "command": "python3",
      "args": [
        "-m",
        "context_search_tool.mcp_server"
      ]
    }
  }
}
```

For stdio MCP transport, server logs must not be written to stdout. The server returns structured tool payloads and leaves stdout for JSON-RPC. Python logging is written to `/tmp/cst-mcp.log` by default; override it with `CST_MCP_LOG_FILE=/path/to/log`.

### MCP Feedback Log

`context_search_query` appends minimal feedback events to:

```text
<repo>/.context-search/mcp_calls.jsonl
```

The log records query text, result count, top score, score parts, summary counts, follow-up keyword count, embedding fingerprint, and error code. It does not record returned source snippets or full file content. When `mcp_calls.jsonl` exceeds 10 MiB, the server rotates it to `mcp_calls.<time_ns>.jsonl` before appending the next event.

Use this log to decide embedding work:

- If endpoint, class, enum, and field searches are strong but Chinese business-description searches miss, test a real embedding provider.
- If the right files appear but ranking is weak, tune reranking before changing embedding.
- If implementation chains are missing, improve Java/MyBatis relation signals before changing embedding.
- Keep `hash-v1` as the default until MCP call evidence shows it is the limiting factor.
````

- [ ] **Step 2: Update current limitation text**

In the Java enhancement limitation list, replace:

```markdown
- MCP server
```

with:

```markdown
- remote MCP deployment or hosted multi-user service
```

- [ ] **Step 3: Verify README contains the new command and no stale limitation**

Run:

```bash
rg -n "cst-mcp|context_search_query|MCP server|remote MCP deployment" README.md
```

Expected output includes the new MCP section, includes `remote MCP deployment or hosted multi-user service`, and has no line that still says local MCP server is unsupported.

- [ ] **Step 4: Commit**

Run:

```bash
git add README.md
git commit -m "docs: describe mcp agent tool usage"
```

---

### Task 6: Run Full Verification And Real MCP Smoke

**Files:**
- No source edits expected.

- [ ] **Step 1: Run the complete test suite**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 2: Run CLI import smoke**

Run:

```bash
python3 -m context_search_tool.cli --help
```

Expected: command help prints and exits with code `0`.

- [ ] **Step 3: Run MCP module import smoke**

Run:

```bash
python3 -c "from context_search_tool.mcp_server import SERVER_NAME; print(SERVER_NAME)"
```

Expected output:

```text
context-search-tool
```

- [ ] **Step 4: Run MCP Inspector manually**

Run:

```bash
npx -y @modelcontextprotocol/inspector
```

In the Inspector UI, configure a stdio server with:

```text
command: cst-mcp
args:
```

Call these tools against `tests/fixtures/java-spring-mini`. Replace `<context-search-tool-repo>` with the absolute path to this repository:

```text
context_search_index(repo="<context-search-tool-repo>/tests/fixtures/java-spring-mini")
context_search_query(repo="<context-search-tool-repo>/tests/fixtures/java-spring-mini", query="/apply/audit/pageEs INVOLVED_BY_ME", context_lines=5, full_file=false, final_top_k=5)
context_search_stats(repo="<context-search-tool-repo>/tests/fixtures/java-spring-mini")
context_search_explain(repo="<context-search-tool-repo>/tests/fixtures/java-spring-mini", location="src/main/java/com/example/audit/ApplyAuditController.java:1")
```

Expected:

- Index call returns `"ok": true`.
- Query call returns ranked results with summary sections.
- Stats call reports embedding provider `hash`.
- Explain call returns chunk metadata.
- `.context-search/mcp_calls.jsonl` contains one query feedback event with no source snippet.

- [ ] **Step 5: Run diff hygiene checks**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 6: Commit any verification-only doc correction**

If Task 6 uncovered a README command typo and only docs were corrected, run:

```bash
git add README.md
git commit -m "docs: fix mcp verification instructions"
```

If no files changed during Task 6, skip this commit.

---

## Embedding Decision Gate After MCP v0

Do not change the default embedding provider during this plan. After MCP v0 is used by agents, review at least 30 real query events from `.context-search/mcp_calls.jsonl`.

Use this decision table:

| Evidence from MCP calls | Next action |
| --- | --- |
| Exact endpoint, class, enum, mapper, and field queries succeed, but Chinese business-description queries return empty or irrelevant results | Create a separate embedding-provider plan using `openai-compatible` or a local embedding service |
| Correct files appear in top 10 but not top 3 | Tune deterministic rerank weights and summary grouping first |
| Controller appears but service/executor/mapper chain is missing | Improve Java/MyBatis relation signals first |
| Top results are mostly tests or stale files | Tune path penalties and legacy/test classification first |
| `hash-v1` performs well on most MCP calls | Keep hash as default and document stronger embedding as an opt-in profile |

Success criteria for starting embedding work:

- At least 30 real MCP query events exist.
- At least 10 misses or partial hits are manually labeled.
- Misses show semantic-language mismatch rather than missing relation extraction.
- A stronger provider can be evaluated against the same query set without changing the MCP tool contract.

---

## Final Verification Checklist

- `pytest -v` passes.
- `python3 -m context_search_tool.cli --help` exits `0`.
- `python3 -c "from context_search_tool.mcp_server import SERVER_NAME; print(SERVER_NAME)"` prints `context-search-tool`.
- MCP Inspector can call all four tools.
- Missing-index query does not create `.context-search/`.
- Query feedback log does not include returned source content.
- README documents `cst-mcp` and the embedding feedback gate.
