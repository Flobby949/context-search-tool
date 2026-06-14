# Query Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional local Ollama query-planning stage that expands difficult cross-language code-search queries before the existing deterministic retrieval pipeline runs.

**Architecture:** Keep query planning as a thin query-time core component. The planner produces bounded hints, retrieval consumes those hints as lower-priority lexical, path, symbol, and signal evidence, and semantic/vector search continues to use only the original query. JSON, CLI Markdown, MCP payloads, and MCP feedback expose planner status without storing full prompt text.

**Tech Stack:** Python 3.11+, dataclasses, Protocol, Typer, requests.Session, SQLite-backed existing retrieval, pytest, existing fake-session test style.

---

## Context

The approved design is `docs/superpowers/specs/2026-06-14-query-planner-design.md`.

Current code shape:

- `src/context_search_tool/config.py` owns `ToolConfig`, default config rendering, and simple TOML parsing.
- `src/context_search_tool/retrieval.py` owns `QueryBundle` and the query flow: semantic candidates, lexical/path/symbol candidates, signal candidates, relation expansion, reranking, context expansion, and summary output.
- `src/context_search_tool/formatters.py` renders `QueryBundle` to Markdown and JSON.
- `src/context_search_tool/cli.py` loads config and calls `query_repository`.
- `src/context_search_tool/mcp_tools.py` calls the same retrieval API and writes content-free query feedback logs.
- Existing focused tests live in `tests/test_config_paths.py`, `tests/test_retrieval_pipeline.py`, `tests/test_formatters.py`, `tests/test_cli_commands.py`, and `tests/test_mcp_tools.py`.

The implementation must not replace retrieval, reranking, indexing, embedding, or relation expansion. It only adds bounded query-time hints before retrieval.

## Assumptions

- The planner is disabled by default.
- The first provider is local Ollama using `qwen3.5:4b-mlx`.
- Missing Ollama, timeout, HTTP errors, invalid JSON, wrong field types, and oversized output all degrade to normal original-query retrieval.
- Planner config is query-time behavior and is not stored in the index manifest.
- Rewritten queries do not trigger extra semantic/vector searches in this milestone.
- `intent` is observability-only in this milestone.
- MCP query input does not gain a planner override in this milestone; MCP follows repo config.
- The real Ollama smoke check is manual and non-CI because local model availability and cold-start latency vary by machine.

## File Map

- Create `src/context_search_tool/query_planner.py`
  - Own planner protocol, prompt constants, prompt hash, query-plan cleanup, disabled/fallback helpers, Ollama client, and planner factory.
- Modify `src/context_search_tool/models.py`
  - Add `QueryPlan`.
- Modify `src/context_search_tool/config.py`
  - Add `QueryPlannerConfig`, render `[query_planner]`, load the section, and teach the simple parser bool and float values.
- Modify `src/context_search_tool/retrieval.py`
  - Add planner metadata to `QueryBundle`, plan before candidate retrieval, split original evidence from planner-hint evidence, and keep planner-hint scores lower than original-query evidence.
- Modify `src/context_search_tool/formatters.py`
  - Add planner diagnostics to JSON and one concise Markdown expansion line when planning succeeds.
- Modify `src/context_search_tool/cli.py`
  - Add `--planner` and `--no-planner` query overrides.
- Modify `src/context_search_tool/mcp_tools.py`
  - Include planner diagnostics in MCP query payloads and feedback logs.
- Test with:
  - `tests/test_config_paths.py`
  - `tests/test_query_planner.py`
  - `tests/test_retrieval_pipeline.py`
  - `tests/test_formatters.py`
  - `tests/test_cli_commands.py`
  - `tests/test_mcp_tools.py`

---

### Task 1: Add Query Planner Config

**Files:**
- Modify: `src/context_search_tool/config.py`
- Test: `tests/test_config_paths.py`

- [ ] **Step 1: Write failing config tests**

Add `QueryPlannerConfig` to the import list in `tests/test_config_paths.py` and add these tests:

```python
def test_render_default_config_contains_query_planner_defaults() -> None:
    rendered = render_default_config()

    assert "[query_planner]" in rendered
    assert "enabled = false" in rendered
    assert 'provider = "ollama"' in rendered
    assert 'model = "qwen3.5:4b-mlx"' in rendered
    assert 'base_url = "http://localhost:11434"' in rendered
    assert "use_system_proxy = false" in rendered
    assert "timeout_seconds = 8.0" in rendered
    assert "max_rewritten_queries = 4" in rendered
    assert "max_keywords = 12" in rendered
    assert "max_symbol_hints = 8" in rendered
    assert DEFAULT_CONFIG.query_planner.enabled is False
```

```python
def test_load_config_reads_query_planner_section(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    ensure_index_layout(repo)
    (repo / ".context-search" / "config.toml").write_text(
        """
[query_planner]
enabled = true
provider = "ollama"
model = "qwen3.5:4b-mlx"
base_url = "http://localhost:11434"
use_system_proxy = true
timeout_seconds = 2.5
max_rewritten_queries = 3
max_keywords = 9
max_symbol_hints = 5
""".lstrip(),
        encoding="utf-8",
    )

    config = load_config(repo)

    assert config.query_planner.enabled is True
    assert config.query_planner.provider == "ollama"
    assert config.query_planner.model == "qwen3.5:4b-mlx"
    assert config.query_planner.base_url == "http://localhost:11434"
    assert config.query_planner.use_system_proxy is True
    assert config.query_planner.timeout_seconds == 2.5
    assert config.query_planner.max_rewritten_queries == 3
    assert config.query_planner.max_keywords == 9
    assert config.query_planner.max_symbol_hints == 5
```

```python
def test_render_config_uses_passed_query_planner_values() -> None:
    rendered = render_config(
        ToolConfig(
            query_planner=QueryPlannerConfig(
                enabled=True,
                provider="ollama",
                model="custom-model",
                base_url="http://127.0.0.1:11434",
                use_system_proxy=True,
                timeout_seconds=1.5,
                max_rewritten_queries=2,
                max_keywords=6,
                max_symbol_hints=4,
            )
        )
    )

    assert "enabled = true" in rendered
    assert 'model = "custom-model"' in rendered
    assert 'base_url = "http://127.0.0.1:11434"' in rendered
    assert "use_system_proxy = true" in rendered
    assert "timeout_seconds = 1.5" in rendered
    assert "max_rewritten_queries = 2" in rendered
    assert "max_keywords = 6" in rendered
    assert "max_symbol_hints = 4" in rendered
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest tests/test_config_paths.py -v
```

Expected: tests fail because `QueryPlannerConfig` and `ToolConfig.query_planner` do not exist yet.

- [ ] **Step 3: Implement config support**

In `src/context_search_tool/config.py`, add:

```python
@dataclass(frozen=True)
class QueryPlannerConfig:
    enabled: bool = False
    provider: str = "ollama"
    model: str = "qwen3.5:4b-mlx"
    base_url: str = "http://localhost:11434"
    use_system_proxy: bool = False
    timeout_seconds: float = 8.0
    max_rewritten_queries: int = 4
    max_keywords: int = 12
    max_symbol_hints: int = 8
```

Extend `ToolConfig`:

```python
@dataclass(frozen=True)
class ToolConfig:
    index: IndexConfig = field(default_factory=IndexConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    query_planner: QueryPlannerConfig = field(default_factory=QueryPlannerConfig)
```

In `render_config`, add a `[query_planner]` section after `[embedding]`:

```python
"[query_planner]",
f"enabled = {_toml_bool(config.query_planner.enabled)}",
f"provider = {_toml_string(config.query_planner.provider)}",
f"model = {_toml_string(config.query_planner.model)}",
f"base_url = {_toml_string(config.query_planner.base_url)}",
f"use_system_proxy = {_toml_bool(config.query_planner.use_system_proxy)}",
f"timeout_seconds = {config.query_planner.timeout_seconds}",
f"max_rewritten_queries = {config.query_planner.max_rewritten_queries}",
f"max_keywords = {config.query_planner.max_keywords}",
f"max_symbol_hints = {config.query_planner.max_symbol_hints}",
"",
```

Add the section to `load_config`:

```python
query_planner=_build_section(
    QueryPlannerConfig,
    data.get("query_planner", {}),
),
```

Add `_toml_bool`:

```python
def _toml_bool(value: bool) -> str:
    return "true" if value else "false"
```

Update `_parse_simple_toml_value` so environments without `tomllib` can read planner booleans and floats:

```python
if value == "true":
    return True
if value == "false":
    return False
try:
    if "." in value:
        return float(value)
    return int(value)
except ValueError:
    return value
```

- [ ] **Step 4: Verify config tests pass**

Run:

```bash
pytest tests/test_config_paths.py -v
```

Expected: all config path tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/context_search_tool/config.py tests/test_config_paths.py
git commit -m "feat: add query planner config"
```

---

### Task 2: Add QueryPlan Model And Planner Cleanup

**Files:**
- Create: `src/context_search_tool/query_planner.py`
- Modify: `src/context_search_tool/models.py`
- Test: `tests/test_query_planner.py`

- [ ] **Step 1: Write failing model and cleanup tests**

Create `tests/test_query_planner.py` with:

```python
from context_search_tool.config import QueryPlannerConfig
from context_search_tool.models import QueryPlan
from context_search_tool.query_planner import (
    PROMPT_VERSION,
    clean_planner_payload,
    disabled_plan,
    fallback_plan,
    prompt_hash,
)


def test_query_plan_defaults_to_disabled() -> None:
    plan = QueryPlan(original_query="数据看板统计图表功能")

    assert plan.status == "disabled"
    assert plan.rewritten_queries == []
    assert plan.grep_keywords == []
    assert plan.symbol_hints == []
    assert plan.intent == "unknown"


def test_clean_planner_payload_strips_dedupes_truncates_and_validates_intent() -> None:
    config = QueryPlannerConfig(
        max_rewritten_queries=2,
        max_keywords=3,
        max_symbol_hints=1,
    )

    plan = clean_planner_payload(
        original_query="数据看板统计图表功能",
        payload={
            "rewritten_queries": [
                " dashboard chart ",
                "Dashboard chart",
                "extra query",
            ],
            "grep_keywords": ["Dashboard", " dashboard ", "", "Chart"],
            "symbol_hints": ["DashboardService", "dashboardservice", "Ignored"],
            "intent": "feature_lookup",
        },
        config=config,
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=42,
    )

    assert plan.status == "ok"
    assert plan.provider == "ollama"
    assert plan.model == "qwen3.5:4b-mlx"
    assert plan.prompt_version == PROMPT_VERSION
    assert plan.prompt_hash == prompt_hash()
    assert plan.latency_ms == 42
    assert plan.rewritten_queries == ["dashboard chart", "extra query"]
    assert plan.grep_keywords == ["Dashboard", "Chart"]
    assert plan.symbol_hints == ["DashboardService"]
    assert plan.intent == "feature_lookup"


def test_clean_planner_payload_falls_back_on_wrong_field_types() -> None:
    plan = clean_planner_payload(
        original_query="数据看板统计图表功能",
        payload={"grep_keywords": "Dashboard"},
        config=QueryPlannerConfig(),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )

    assert plan.status == "fallback"
    assert "grep_keywords must be a list" in (plan.error or "")


def test_clean_planner_payload_uses_unknown_for_unknown_intent() -> None:
    plan = clean_planner_payload(
        original_query="数据看板统计图表功能",
        payload={"intent": "invented"},
        config=QueryPlannerConfig(),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )

    assert plan.status == "ok"
    assert plan.intent == "unknown"


def test_clean_planner_payload_uses_unknown_for_non_string_intent() -> None:
    plan = clean_planner_payload(
        original_query="数据看板统计图表功能",
        payload={"intent": 123},
        config=QueryPlannerConfig(),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )

    assert plan.status == "ok"
    assert plan.intent == "unknown"


def test_clean_planner_payload_returns_empty_lists_when_limits_are_not_positive() -> None:
    plan = clean_planner_payload(
        original_query="query",
        payload={
            "rewritten_queries": ["one", "two"],
            "grep_keywords": ["A", "B"],
            "symbol_hints": ["Service", "Controller"],
        },
        config=QueryPlannerConfig(
            max_rewritten_queries=0,
            max_keywords=0,
            max_symbol_hints=-1,
        ),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )

    assert plan.status == "ok"
    assert plan.rewritten_queries == []
    assert plan.grep_keywords == []
    assert plan.symbol_hints == []


def test_disabled_and_fallback_helpers_include_diagnostics() -> None:
    disabled = disabled_plan("query")
    fallback = fallback_plan(
        "query",
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=8,
        error="planner timed out after 8 seconds",
    )

    assert disabled.status == "disabled"
    assert fallback.status == "fallback"
    assert fallback.latency_ms == 8
    assert fallback.error == "planner timed out after 8 seconds"
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest tests/test_query_planner.py -v
```

Expected: import failures because `QueryPlan` and `query_planner.py` do not exist yet.

- [ ] **Step 3: Add `QueryPlan`**

In `src/context_search_tool/models.py`, add:

```python
@dataclass(frozen=True)
class QueryPlan:
    original_query: str
    rewritten_queries: list[str] = field(default_factory=list)
    grep_keywords: list[str] = field(default_factory=list)
    symbol_hints: list[str] = field(default_factory=list)
    intent: str = "unknown"
    status: str = "disabled"
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    prompt_hash: str = ""
    latency_ms: int | None = None
    error: str | None = None

    @staticmethod
    def disabled_default() -> QueryPlan:
        return QueryPlan(original_query="", status="disabled")
```

- [ ] **Step 4: Add planner cleanup module**

Create `src/context_search_tool/query_planner.py` with:

```python
from __future__ import annotations

import hashlib
from typing import Any, Protocol

from context_search_tool.config import QueryPlannerConfig
from context_search_tool.models import QueryPlan

PROMPT_VERSION = "qwen-query-planner-v1"

ALLOWED_INTENTS = {
    "feature_lookup",
    "endpoint_lookup",
    "bug_trace",
    "data_flow",
    "symbol_lookup",
    "unknown",
}

SYSTEM_PROMPT = """You rewrite code-search queries. Return only compact JSON matching the schema.
Do not explain. Do not guess file paths. Prefer identifiers and English code terms.

DO NOT:
- Add file paths such as src/main/java/com/example/Foo.java.
- Add framework annotations such as @Autowired, @Service, or @RequestMapping.
- Add implementation details such as extends BaseController.
- Repeat the original query verbatim in rewritten_queries.
- Return prose or Markdown.

DO:
- Add English code terms for Chinese business words.
- Use likely class or method names only when strongly implied.
- Keep keywords concise."""


class QueryPlanner(Protocol):
    def plan(self, query: str) -> QueryPlan:
        ...


def prompt_hash() -> str:
    digest = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def disabled_plan(query: str) -> QueryPlan:
    return QueryPlan(original_query=query, status="disabled")


def fallback_plan(
    query: str,
    provider: str,
    model: str,
    latency_ms: int | None,
    error: str,
) -> QueryPlan:
    return QueryPlan(
        original_query=query,
        status="fallback",
        provider=provider,
        model=model,
        prompt_version=PROMPT_VERSION,
        prompt_hash=prompt_hash(),
        latency_ms=latency_ms,
        error=error,
    )


def clean_planner_payload(
    original_query: str,
    payload: dict[str, Any],
    config: QueryPlannerConfig,
    provider: str,
    model: str,
    latency_ms: int | None,
) -> QueryPlan:
    try:
        rewritten_queries = _clean_string_list(
            payload,
            "rewritten_queries",
            config.max_rewritten_queries,
        )
        grep_keywords = _clean_string_list(
            payload,
            "grep_keywords",
            config.max_keywords,
        )
        symbol_hints = _clean_string_list(
            payload,
            "symbol_hints",
            config.max_symbol_hints,
        )
    except ValueError as exc:
        return fallback_plan(
            original_query,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            error=str(exc),
        )

    raw_intent = payload.get("intent", "unknown")
    intent = raw_intent if isinstance(raw_intent, str) and raw_intent in ALLOWED_INTENTS else "unknown"
    return QueryPlan(
        original_query=original_query,
        rewritten_queries=rewritten_queries,
        grep_keywords=grep_keywords,
        symbol_hints=symbol_hints,
        intent=intent,
        status="ok",
        provider=provider,
        model=model,
        prompt_version=PROMPT_VERSION,
        prompt_hash=prompt_hash(),
        latency_ms=latency_ms,
    )


def _clean_string_list(payload: dict[str, Any], key: str, limit: int) -> list[str]:
    if limit <= 0:
        return []
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{key} must contain only strings")
        stripped = item.strip()
        normalized = stripped.lower()
        if not normalized or normalized in seen:
            continue
        cleaned.append(stripped)
        seen.add(normalized)
        if len(cleaned) >= limit:
            break
    return cleaned
```

- [ ] **Step 5: Verify focused tests pass**

Run:

```bash
pytest tests/test_query_planner.py -v
```

Expected: all query planner tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/context_search_tool/models.py src/context_search_tool/query_planner.py tests/test_query_planner.py
git commit -m "feat: add query planner model"
```

---

### Task 3: Add Local Ollama Planner Client

**Files:**
- Modify: `src/context_search_tool/query_planner.py`
- Test: `tests/test_query_planner.py`

- [ ] **Step 1: Add failing Ollama client tests**

Append these tests to `tests/test_query_planner.py`:

```python
import json

import requests

from context_search_tool.query_planner import OllamaQueryPlanner, planner_from_config


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, object]:
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response
        self.trust_env = True
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_ollama_planner_parses_valid_json_and_bypasses_proxy() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            {
                "message": {
                    "content": json.dumps(
                        {
                            "rewritten_queries": ["数据看板 dashboard statistics chart"],
                            "grep_keywords": ["Dashboard", "Statistics", "Chart"],
                            "symbol_hints": ["DashboardController"],
                            "intent": "feature_lookup",
                        }
                    )
                }
            },
        )
    )
    config = QueryPlannerConfig(enabled=True, timeout_seconds=1.5)
    planner = OllamaQueryPlanner(config, session=session)

    plan = planner.plan("数据看板统计图表功能")

    assert plan.status == "ok"
    assert plan.grep_keywords == ["Dashboard", "Statistics", "Chart"]
    assert plan.symbol_hints == ["DashboardController"]
    assert session.trust_env is False
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == "http://localhost:11434/api/chat"
    assert call["timeout"] == 1.5
    assert call["json"]["model"] == "qwen3.5:4b-mlx"
    assert call["json"]["stream"] is False


def test_ollama_planner_honors_use_system_proxy() -> None:
    session = FakeSession(FakeResponse(200, {"message": {"content": "{}"}}))
    config = QueryPlannerConfig(enabled=True, use_system_proxy=True)
    planner = OllamaQueryPlanner(config, session=session)

    plan = planner.plan("query")

    assert plan.status == "ok"
    assert session.trust_env is True


def test_ollama_planner_falls_back_on_timeout_without_retry() -> None:
    session = FakeSession(requests.Timeout("slow"))
    config = QueryPlannerConfig(enabled=True, timeout_seconds=0.01)
    planner = OllamaQueryPlanner(config, session=session)

    plan = planner.plan("query")

    assert plan.status == "fallback"
    assert "planner timed out" in (plan.error or "")
    assert len(session.calls) == 1


def test_ollama_planner_falls_back_on_invalid_json_content() -> None:
    session = FakeSession(FakeResponse(200, {"message": {"content": "not json"}}))
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("query")

    assert plan.status == "fallback"
    assert "invalid planner JSON" in (plan.error or "")


def test_ollama_planner_falls_back_on_http_error_without_retry() -> None:
    session = FakeSession(FakeResponse(500, {"message": {"content": "{}"}}))
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("query")

    assert plan.status == "fallback"
    assert "planner HTTP error" in (plan.error or "")
    assert len(session.calls) == 1


def test_planner_from_config_returns_disabled_planner_when_disabled() -> None:
    planner = planner_from_config(QueryPlannerConfig(enabled=False))

    assert planner.plan("query").status == "disabled"
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
pytest tests/test_query_planner.py -v
```

Expected: tests fail because `OllamaQueryPlanner` and `planner_from_config` do not exist.

- [ ] **Step 3: Implement Ollama client**

Extend `src/context_search_tool/query_planner.py` with:

```python
import json
import time

import requests
```

Add:

```python
class DisabledQueryPlanner:
    def plan(self, query: str) -> QueryPlan:
        return disabled_plan(query)


class OllamaQueryPlanner:
    def __init__(
        self,
        config: QueryPlannerConfig,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.session.trust_env = config.use_system_proxy

    def plan(self, query: str) -> QueryPlan:
        start = time.perf_counter()
        try:
            response = self.session.post(
                f"{self.config.base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.config.model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(_user_payload(query, self.config), ensure_ascii=False)},
                    ],
                },
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            raw_content = response.json().get("message", {}).get("content", "")
            if not isinstance(raw_content, str):
                return self._fallback(query, start, "planner response content must be a string")
            try:
                payload = json.loads(raw_content)
            except json.JSONDecodeError:
                return self._fallback(query, start, "invalid planner JSON")
            if not isinstance(payload, dict):
                return self._fallback(query, start, "planner JSON must be an object")
            return clean_planner_payload(
                original_query=query,
                payload=payload,
                config=self.config,
                provider=self.config.provider,
                model=self.config.model,
                latency_ms=_elapsed_ms(start),
            )
        except requests.Timeout:
            return self._fallback(
                query,
                start,
                f"planner timed out after {self.config.timeout_seconds:g} seconds",
            )
        except requests.HTTPError as exc:
            return self._fallback(query, start, f"planner HTTP error: {exc}")
        except requests.RequestException as exc:
            return self._fallback(query, start, f"planner request failed: {exc}")

    def _fallback(self, query: str, start: float, error: str) -> QueryPlan:
        return fallback_plan(
            query,
            provider=self.config.provider,
            model=self.config.model,
            latency_ms=_elapsed_ms(start),
            error=error,
        )


def planner_from_config(config: QueryPlannerConfig) -> QueryPlanner:
    if not config.enabled:
        return DisabledQueryPlanner()
    if config.provider != "ollama":
        return DisabledQueryPlanner()
    return OllamaQueryPlanner(config)


def _user_payload(query: str, config: QueryPlannerConfig) -> dict[str, object]:
    return {
        "query": query,
        "language_hints": ["Java", "Spring"],
        "max_rewritten_queries": config.max_rewritten_queries,
        "max_keywords": config.max_keywords,
        "max_symbol_hints": config.max_symbol_hints,
    }


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
```

If `planner_from_config` should treat unsupported providers as fallback instead of disabled, add a focused test first. For this milestone, keep unsupported provider behavior simple and disabled because config defaults to `ollama`.

Implementation note:

- Keep the session instance-scoped. Do not add a module-level or class-level singleton session in this milestone.
- The injected session is intentionally mutated with `trust_env = config.use_system_proxy`; the fake-session tests assert both proxy modes.
- If a later server process wants connection reuse across many queries, reuse one `OllamaQueryPlanner` instance rather than adding global mutable state.

- [ ] **Step 4: Verify focused tests pass**

Run:

```bash
pytest tests/test_query_planner.py -v
```

Expected: all query planner tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/context_search_tool/query_planner.py tests/test_query_planner.py
git commit -m "feat: add ollama query planner"
```

---

### Task 4: Wire Planner Into Retrieval

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Test: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add failing retrieval tests with a fake planner**

Append these helpers and tests to `tests/test_retrieval_pipeline.py`:

```python
from context_search_tool.models import QueryPlan


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
```

Add the first retrieval behavior test:

```python
def test_query_planner_hints_surface_dashboard_code_for_chinese_query(tmp_path: Path) -> None:
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
    assert any(result.file_path == Path("DashboardController.java") for result in bundle.results)
    dashboard = next(result for result in bundle.results if result.file_path == Path("DashboardController.java"))
    assert "planner hint match" in dashboard.reasons
```

Add the fallback behavior test:

```python
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
    assert bundle.expanded_tokens == ["targettoken"]
    assert bundle.results[0].file_path == Path("OriginalMatch.java")
```

Add the ranking safety test:

```python
def test_planner_only_match_ranks_below_comparable_original_match(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OriginalDashboard.java").write_text(
        'class OriginalDashboard { String value = "targetToken"; }\n',
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
        Path("OriginalDashboard.java"),
        Path("PlannerDashboard.java"),
    ]
    assert "planner hint match" not in bundle.results[0].reasons
    assert "planner hint match" in bundle.results[1].reasons
```

- [ ] **Step 2: Run focused retrieval tests and verify failure**

Run:

```bash
pytest tests/test_retrieval_pipeline.py -v
```

Expected: new tests fail because `query_repository` has no planner parameter and `QueryBundle` has no planner field.

- [ ] **Step 3: Extend `QueryBundle`**

In `src/context_search_tool/retrieval.py`, import `QueryPlan`, `QueryPlanner`, `expand_query_plan_tokens`, `planner_hint_tokens`, and `planner_from_config` after those helpers exist.

Update `QueryBundle`:

```python
@dataclass(frozen=True)
class QueryBundle:
    query: str
    expanded_tokens: list[str]
    results: list[RetrievalResult]
    followup_keywords: list[str]
    summary: RetrievalSummary = field(default_factory=RetrievalSummary)
    planner: QueryPlan = field(default_factory=QueryPlan.disabled_default)
```

Use explicit `planner=plan` in every `QueryBundle` return inside `query_repository`.

- [ ] **Step 4: Add query expansion helper**

In `src/context_search_tool/query_planner.py`, add:

```python
from context_search_tool.tokenizer import tokenize_query


def expand_query_plan_tokens(query: str, plan: QueryPlan) -> list[str]:
    original_tokens = _dedupe(tokenize_query(query))
    if plan.status != "ok":
        return original_tokens
    expanded: list[str] = []
    for rewritten_query in plan.rewritten_queries:
        expanded.extend(tokenize_query(rewritten_query))
    expanded.extend(plan.grep_keywords)
    expanded.extend(plan.symbol_hints)
    return _dedupe([*original_tokens, *expanded])


def planner_hint_tokens(original_tokens: list[str], expanded_tokens: list[str]) -> list[str]:
    original = {token.lower() for token in original_tokens}
    return [token for token in expanded_tokens if token.lower() not in original]


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        normalized = token.lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped
```

Add unit coverage in `tests/test_query_planner.py`:

```python
from context_search_tool.query_planner import expand_query_plan_tokens, planner_hint_tokens


def test_expand_query_plan_tokens_keeps_original_tokens_first() -> None:
    plan = QueryPlan(
        original_query="数据看板统计图表功能",
        rewritten_queries=["数据看板 dashboard statistics chart"],
        grep_keywords=["Dashboard", "Chart"],
        symbol_hints=["DashboardController"],
        status="ok",
    )

    tokens = expand_query_plan_tokens("数据看板统计图表功能", plan)

    assert tokens[:1] == ["数据看板统计图表功能"]
    assert "dashboard" in tokens
    assert "dashboardcontroller" in tokens
    assert planner_hint_tokens(["数据看板统计图表功能"], tokens)
```

- [ ] **Step 5: Split original evidence from planner-hint evidence**

First verify the current retrieval helper shape:

```bash
rg -n "def _merge_candidates|def _signal_candidates|_signal_candidates\\(" src/context_search_tool/retrieval.py
```

Expected:

- `_merge_candidates` already exists and returns `dict[str, RetrievalCandidate]`; do not replace it with a list-returning helper.
- Existing `_signal_candidates` call sites are in `query_repository` and the new planner helper added below.

Update `query_repository` signature:

```python
def query_repository(
    repo: Path,
    query: str,
    config: ToolConfig,
    context_lines: int | None = None,
    full_file: bool = False,
    planner: QueryPlanner | None = None,
) -> QueryBundle:
```

Update `query_repository` setup:

```python
original_tokens = _dedupe(tokenize_query(query))
query_planner = planner or planner_from_config(config.query_planner)
plan = query_planner.plan(query)
tokens = expand_query_plan_tokens(query, plan)
hint_tokens = planner_hint_tokens(original_tokens, tokens)
```

Keep semantic search original-only. Replace the direct candidate block with:

```python
initial_candidates = _initial_candidates(
    index_dir,
    store,
    query,
    original_tokens,
    config,
    deleted_ids,
)
signal_candidates = _signal_candidates(store, original_tokens, config, planner_hint=False)
planner_candidates = _planner_hint_candidates(store, hint_tokens, config)
direct_candidates = _merge_candidates(
    [*initial_candidates, *signal_candidates, *planner_candidates]
)
```

Change `_initial_candidates` so it receives original tokens only:

```python
def _initial_candidates(
    index_dir: Path,
    store: SQLiteStore,
    query: str,
    original_tokens: list[str],
    config: ToolConfig,
    deleted_ids: set[str],
) -> list[RetrievalCandidate]:
    return [
        *_semantic_candidates(index_dir, query, config, deleted_ids),
        *_lexical_candidates(store, original_tokens, config.retrieval.lexical_top_k),
        *store.path_symbol_search(original_tokens, config.retrieval.lexical_top_k),
    ]
```

Add planner-hint candidate helpers:

```python
def _planner_hint_candidates(
    store: SQLiteStore,
    hint_tokens: list[str],
    config: ToolConfig,
) -> list[RetrievalCandidate]:
    if not hint_tokens:
        return []
    path_symbol = [
        RetrievalCandidate(
            chunk_id=item.chunk_id,
            score=item.score,
            source="planner_path_symbol",
            score_parts={"planner_path_symbol": item.score},
        )
        for item in store.path_symbol_search(hint_tokens, config.retrieval.lexical_top_k)
    ]
    lexical = [
        RetrievalCandidate(
            chunk_id=item.chunk_id,
            score=item.score,
            source="planner_lexical",
            score_parts={"planner_lexical": item.score},
        )
        for item in _lexical_candidates(store, hint_tokens, config.retrieval.lexical_top_k)
    ]
    signals = _signal_candidates(store, hint_tokens, config, planner_hint=True)
    return [*lexical, *path_symbol, *signals]
```

Change `_signal_candidates`:

```python
def _signal_candidates(
    store: SQLiteStore,
    tokens: list[str],
    config: ToolConfig,
    planner_hint: bool = False,
) -> list[RetrievalCandidate]:
    limit = max(
        config.retrieval.semantic_top_k,
        config.retrieval.lexical_top_k,
        config.retrieval.final_top_k,
    )
    source = "planner_signal" if planner_hint else "signal"
    score_key = "planner_signal" if planner_hint else "signal"
    candidates: list[RetrievalCandidate] = []
    for signal in store.signal_search(tokens, limit):
        score = _signal_score(signal.name, signal.tokens, signal.metadata, tokens)
        if score <= 0:
            continue
        candidates.append(
            RetrievalCandidate(
                chunk_id=signal.chunk_id,
                score=score,
                source=source,
                score_parts={score_key: score},
            )
        )
    return candidates
```

- [ ] **Step 6: Add planner-hint scoring and reason**

Update `_candidate_relation_seed_score`:

```python
planner_signal_score = candidate.score_parts.get("planner_signal", 0.0)
if planner_signal_score > 0:
    return _bounded_score(planner_signal_score) * 0.65
```

Update `_combined_score`:

```python
+ (score_parts.get("planner_lexical", 0.0) * 0.12)
+ (min(score_parts.get("planner_path_symbol", 0.0), 5.0) / 5.0 * 0.07)
+ (_bounded_score(score_parts.get("planner_signal", 0.0)) * 0.65)
```

Update `_rank_tier` so planner-only matches are demoted after the current code has assigned its base tier. Keep the existing function signature and store-backed endpoint check:

```python
def _rank_tier(
    store: SQLiteStore,
    chunk: DocumentChunk,
    score_parts: dict[str, float],
) -> int:
    if score_parts.get("signal", 0.0) > 0 and _chunk_has_signal_kind(
        store,
        chunk.chunk_id,
        "endpoint",
    ):
        base_tier = 0
    elif score_parts.get("relation", 0.0) > 0:
        base_tier = 1
    elif score_parts.get("signal", 0.0) > 0:
        base_tier = 2
    else:
        base_tier = 3

    if _is_planner_hint_only(score_parts):
        return base_tier + 1
    return base_tier
```

Add helpers:

```python
def _has_planner_hint(score_parts: dict[str, float]) -> bool:
    return any(
        score_parts.get(key, 0.0) > 0
        for key in ("planner_lexical", "planner_path_symbol", "planner_signal")
    )


def _has_original_query_evidence(score_parts: dict[str, float]) -> bool:
    return any(
        score_parts.get(key, 0.0) > 0
        for key in ("semantic", "lexical", "path_symbol", "signal", "token_coverage")
    )


def _is_planner_hint_only(score_parts: dict[str, float]) -> bool:
    return _has_planner_hint(score_parts) and not _has_original_query_evidence(score_parts)
```

Update `_reasons`:

```python
if _has_planner_hint(score_parts):
    reasons.append("planner hint match")
```

- [ ] **Step 7: Verify retrieval behavior**

Run:

```bash
pytest tests/test_query_planner.py tests/test_retrieval_pipeline.py -v
```

Expected: all query planner and retrieval pipeline tests pass.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/context_search_tool/query_planner.py src/context_search_tool/retrieval.py tests/test_query_planner.py tests/test_retrieval_pipeline.py
git commit -m "feat: apply query planner hints in retrieval"
```

---

### Task 5: Add Planner Diagnostics To Formatters

**Files:**
- Modify: `src/context_search_tool/formatters.py`
- Test: `tests/test_formatters.py`

- [ ] **Step 1: Add failing formatter tests**

Update `sample_bundle()` in `tests/test_formatters.py` only if needed by using explicit planner data in individual tests. Add:

```python
from context_search_tool.models import QueryPlan
```

Add JSON diagnostics test:

```python
def test_json_formatter_includes_planner_diagnostics() -> None:
    bundle = QueryBundle(
        query="数据看板统计图表功能",
        expanded_tokens=["数据看板统计图表功能", "dashboard"],
        followup_keywords=[],
        results=[],
        planner=QueryPlan(
            original_query="数据看板统计图表功能",
            rewritten_queries=["数据看板 dashboard statistics chart"],
            grep_keywords=["Dashboard"],
            symbol_hints=["DashboardController"],
            intent="feature_lookup",
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1200,
        ),
    )

    parsed = json.loads(format_json(bundle))

    assert parsed["planner"] == {
        "enabled": True,
        "provider": "ollama",
        "model": "qwen3.5:4b-mlx",
        "prompt_version": "qwen-query-planner-v1",
        "prompt_hash": "sha256:test",
        "status": "ok",
        "latency_ms": 1200,
        "rewritten_queries": ["数据看板 dashboard statistics chart"],
        "grep_keywords": ["Dashboard"],
        "symbol_hints": ["DashboardController"],
        "intent": "feature_lookup",
    }
```

Add Markdown success-line test:

```python
def test_markdown_formatter_includes_concise_planner_line_when_ok() -> None:
    bundle = QueryBundle(
        query="数据看板统计图表功能",
        expanded_tokens=["数据看板统计图表功能", "dashboard"],
        followup_keywords=[],
        results=[],
        planner=QueryPlan(
            original_query="数据看板统计图表功能",
            grep_keywords=["Dashboard", "Statistics", "Chart"],
            symbol_hints=["DashboardController", "DashboardService"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
        ),
    )

    output = format_markdown(bundle)

    assert (
        "Query expanded by qwen3.5:4b-mlx: "
        "DashboardController, DashboardService, Dashboard, ... (+2 more)"
    ) in output
```

Add fallback silence test:

```python
def test_markdown_formatter_stays_silent_on_planner_fallback() -> None:
    bundle = QueryBundle(
        query="targetToken",
        expanded_tokens=["targettoken"],
        followup_keywords=[],
        results=[],
        planner=QueryPlan(
            original_query="targetToken",
            status="fallback",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            error="planner timed out after 8 seconds",
        ),
    )

    output = format_markdown(bundle)

    assert "Query expanded by" not in output
```

- [ ] **Step 2: Run focused formatter tests and verify failure**

Run:

```bash
pytest tests/test_formatters.py -v
```

Expected: new tests fail because formatter output has no planner field or planner line.

- [ ] **Step 3: Implement planner payload helper**

In `src/context_search_tool/formatters.py`, import `QueryPlan` if needed and add:

```python
def _planner_payload(plan: QueryPlan) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "enabled": plan.status != "disabled",
        "provider": plan.provider,
        "model": plan.model,
        "prompt_version": plan.prompt_version,
        "prompt_hash": plan.prompt_hash,
        "status": plan.status,
        "latency_ms": plan.latency_ms,
    }
    if plan.status == "ok":
        payload.update(
            {
                "rewritten_queries": plan.rewritten_queries,
                "grep_keywords": plan.grep_keywords,
                "symbol_hints": plan.symbol_hints,
                "intent": plan.intent,
            }
        )
    if plan.status == "fallback":
        payload["error"] = plan.error
    return payload
```

Add `"planner": _planner_payload(bundle.planner)` to `format_json`.

Add a Markdown line immediately after `Expanded tokens` when `bundle.planner.status == "ok"`:

```python
planner_line = _planner_markdown_line(bundle.planner)
lines = [
    "# Context Search Results",
    "",
    f"Query: {bundle.query}",
    f"Expanded tokens: {_format_list(bundle.expanded_tokens)}",
    *([planner_line, ""] if planner_line else [""]),
    "## Summary",
    "### Likely Entry Points",
    *_format_bullets(list(bundle.summary.entry_points)),
    "### Likely Implementation",
    *_format_bullets(list(bundle.summary.implementation)),
    "### Related Types",
    *_format_bullets(list(bundle.summary.related_types)),
    "### Possibly Legacy",
    *_format_bullets(list(bundle.summary.possibly_legacy)),
    "",
    "## Results",
]
```

Use this helper:

```python
def _planner_markdown_line(plan: QueryPlan) -> str:
    if plan.status != "ok":
        return ""
    hints = [*plan.symbol_hints[:2], *plan.grep_keywords[:2]][:3]
    if not hints:
        return f"Query expanded by {plan.model}."
    hint_text = ", ".join(hints)
    total_hints = len(plan.symbol_hints) + len(plan.grep_keywords)
    if total_hints > 3:
        hint_text += f", ... (+{total_hints - 3} more)"
    return f"Query expanded by {plan.model}: {hint_text}"
```

- [ ] **Step 4: Verify formatter tests**

Run:

```bash
pytest tests/test_formatters.py -v
```

Expected: all formatter tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/context_search_tool/formatters.py tests/test_formatters.py
git commit -m "feat: expose query planner diagnostics"
```

---

### Task 6: Add CLI Planner Overrides

**Files:**
- Modify: `src/context_search_tool/cli.py`
- Test: `tests/test_cli_commands.py`

- [ ] **Step 1: Add failing CLI tests**

Add:

```python
def test_query_rejects_conflicting_planner_flags(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["index", str(repo)]).exit_code == 0

    result = runner.invoke(
        app,
        ["query", str(repo), "App", "--planner", "--no-planner"],
    )

    assert result.exit_code == 1
    assert "Error: --planner and --no-planner cannot be used together" in result.output
```

Add:

```python
def test_query_no_planner_overrides_enabled_config(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["index", str(repo)]).exit_code == 0
    config_path = repo / ".context-search" / "config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "enabled = false",
            "enabled = true",
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["query", str(repo), "App", "--json", "--no-planner"])

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["planner"]["status"] == "disabled"
```

- [ ] **Step 2: Run focused CLI tests and verify failure**

Run:

```bash
pytest tests/test_cli_commands.py -v
```

Expected: new tests fail because the flags do not exist.

- [ ] **Step 3: Implement CLI options**

In `src/context_search_tool/cli.py`, import `replace`:

```python
from dataclasses import replace
```

Add options to `query`:

```python
planner: bool = typer.Option(False, "--planner", help="Force query planner on."),
no_planner: bool = typer.Option(False, "--no-planner", help="Force query planner off."),
```

After `config = load_config(repo)`, add:

```python
if planner and no_planner:
    typer.echo("Error: --planner and --no-planner cannot be used together", err=True)
    raise typer.Exit(code=1)
if planner or no_planner:
    config = replace(
        config,
        query_planner=replace(config.query_planner, enabled=planner),
    )
```

- [ ] **Step 4: Verify CLI tests**

Run:

```bash
pytest tests/test_cli_commands.py -v
```

Expected: all CLI command tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/context_search_tool/cli.py tests/test_cli_commands.py
git commit -m "feat: add query planner cli overrides"
```

---

### Task 7: Add Planner Metadata To MCP Payload And Feedback

**Files:**
- Modify: `src/context_search_tool/mcp_tools.py`
- Test: `tests/test_mcp_tools.py`

- [ ] **Step 1: Add failing MCP payload and feedback tests**

Add:

```python
def test_mcp_query_payload_includes_planner_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_query_tool(str(repo), "/apply/audit/pageEs")

    assert result["ok"] is True
    assert result["planner"]["status"] == "disabled"
    assert result["planner"]["enabled"] is False
```

Add:

```python
def test_mcp_query_feedback_includes_planner_metadata_without_prompt_text(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_query_tool(str(repo), "/apply/audit/pageEs")

    assert result["ok"] is True
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    event = events[0]
    assert event["planner"]["status"] == "disabled"
    assert "prompt" not in json.dumps(event).lower()
```

- [ ] **Step 2: Run focused MCP tests and verify failure**

Run:

```bash
pytest tests/test_mcp_tools.py -v
```

Expected: new tests fail because MCP payload and feedback do not include planner metadata.

- [ ] **Step 3: Reuse formatter-style planner payload**

In `src/context_search_tool/mcp_tools.py`, add a private helper:

```python
def _planner_payload(bundle: QueryBundle) -> dict[str, Any]:
    plan = bundle.planner
    payload: dict[str, Any] = {
        "enabled": plan.status != "disabled",
        "provider": plan.provider,
        "model": plan.model,
        "prompt_version": plan.prompt_version,
        "prompt_hash": plan.prompt_hash,
        "status": plan.status,
        "latency_ms": plan.latency_ms,
    }
    if plan.status == "ok":
        payload.update(
            {
                "rewritten_queries": plan.rewritten_queries,
                "grep_keywords": plan.grep_keywords,
                "symbol_hints": plan.symbol_hints,
                "intent": plan.intent,
            }
        )
    if plan.status == "fallback":
        payload["error"] = plan.error
    return payload
```

Add `"planner": _planner_payload(bundle)` in `_query_payload`.

In `_append_query_feedback`, add:

```python
"planner": _feedback_planner_payload(payload),
```

Add:

```python
def _feedback_planner_payload(payload: dict[str, Any]) -> dict[str, Any]:
    planner = dict(payload.get("planner", {}))
    return {
        key: planner.get(key)
        for key in (
            "enabled",
            "provider",
            "model",
            "prompt_version",
            "prompt_hash",
            "status",
            "latency_ms",
            "intent",
            "error",
        )
        if key in planner
    }
```

Do not include full prompt text or source content in feedback.

- [ ] **Step 4: Verify MCP tests**

Run:

```bash
pytest tests/test_mcp_tools.py -v
```

Expected: all MCP tool tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/context_search_tool/mcp_tools.py tests/test_mcp_tools.py
git commit -m "feat: include planner metadata in mcp query"
```

---

### Task 8: Run Full Verification And Manual Smoke

**Files:**
- No required source changes.
- Optional: append a short manual smoke note to `docs/superpowers/plans/2026-06-14-query-planner.md` only if the real Ollama check is executed during implementation.

- [ ] **Step 1: Run the full test suite**

Run:

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run planner-disabled CLI sanity**

Run:

```bash
cst query /Users/flobby/Documents/context-seatch-tool "query planner" --json --no-planner
```

Expected: command exits successfully if the repo is indexed, and JSON contains:

```json
{
  "planner": {
    "enabled": false,
    "status": "disabled"
  }
}
```

If the repo is not indexed, first run:

```bash
cst index /Users/flobby/Documents/context-seatch-tool
```

Then rerun the query command.

- [ ] **Step 3: Run optional real Ollama smoke if the model is installed**

Run:

```bash
ollama list
```

Expected: `qwen3.5:4b-mlx` appears in the model list. If it does not appear, skip this smoke and record `Skipped: qwen3.5:4b-mlx not installed`.

Choose a smoke repo:

```bash
test -d /Users/flobby/work/code/operation-admin-api
```

If the command succeeds, use:

```bash
TEST_REPO=/Users/flobby/work/code/operation-admin-api
```

If it fails, check the fallback repo:

```bash
test -d /Users/flobby/work/code/irs-portal-base
```

If that command succeeds, use:

```bash
TEST_REPO=/Users/flobby/work/code/irs-portal-base
```

If both repo checks fail, skip this smoke and record `Skipped: no smoke repo available`.

Run the smoke query:

```bash
cst index "$TEST_REPO"
cst query "$TEST_REPO" "数据看板统计图表功能" --planner --json
```

Expected:

- JSON has `planner.status` equal to `ok` or `fallback`.
- If `planner.status` is `ok`, `planner.grep_keywords` or `planner.symbol_hints` include dashboard-related hints.
- If `TEST_REPO` is `/Users/flobby/work/code/operation-admin-api`, `DashboardController`, `DashboardService`, or `DashboardServiceImpl` appears in Top 5 when that repo contains those symbols.
- If `TEST_REPO` is `/Users/flobby/work/code/irs-portal-base`, treat the run as a planner health check only, because that repo may not contain the same dashboard classes.

If the smoke is actually run, append a short note near the end of this plan:

```markdown
## Manual Smoke Test Result

- Date: 2026-06-14
- Model: qwen3.5:4b-mlx available: yes/no
- Test repo: path or none available
- Planner status: ok/fallback/skipped
- Top result: file path or N/A
```

- [ ] **Step 4: Check for formatting and leftover markers**

Run:

```bash
rg -n "T[B]D|T[O]DO|implement lat[e]r|fill in detail[s]|Add appropr[i]ate|Write tests for the ab[o]ve" docs/superpowers/plans/2026-06-14-query-planner.md src/context_search_tool tests
```

Expected: no matches related to this implementation.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git diff --stat
git diff --check
```

Expected: diff contains only planner-related files and `git diff --check` reports no whitespace errors.

- [ ] **Step 6: Commit verification notes if this task modified the plan**

If Step 3 added a manual smoke note to this plan, run:

```bash
git add docs/superpowers/plans/2026-06-14-query-planner.md
git commit -m "docs: record query planner smoke result"
```

If no notes were added, skip this commit.

---

## Acceptance Criteria

- Existing tests pass with planner disabled.
- Query planner is disabled by default.
- Enabling planner does not require reindexing.
- Planner failure degrades to original query retrieval.
- Semantic/vector search still runs only for the original query.
- Planner hints affect lexical, path, symbol, signal, and relation-seed retrieval with lower priority than original-query evidence.
- Planner-only matches include `planner hint match`.
- JSON output includes planner status for disabled, ok, and fallback states.
- Markdown output includes one concise expansion line only when planning succeeds.
- CLI supports `--planner` and `--no-planner`, and rejects using both together.
- MCP query payload includes planner diagnostics.
- MCP feedback logs include planner metadata but not full prompt text or source content.
- Fake planner tests prove Chinese `数据看板统计图表功能` can surface Dashboard fixture code through planner hints.
- Fake fallback tests prove original-query retrieval still works after planner failure.
- Optional real Ollama smoke is recorded as passed, skipped due to missing model, or skipped due to missing target repo.
