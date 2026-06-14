# Query Planner Design

Date: 2026-06-14
Status: Draft for review
Repository: `/Users/flobby/Documents/context-seatch-tool`

## Summary

Add an optional local LLM query-planning stage before the existing retrieval pipeline. The planner uses the installed Ollama model `qwen3.5:4b-mlx` to turn a natural-language question into a small, structured retrieval plan: rewritten queries, cross-language keywords, likely symbols, and intent hints.

The planner does not replace CST's existing hybrid retrieval. It expands the search surface before semantic, lexical, symbol, signal, and relation stages run. Ranking and evidence remain deterministic and explainable inside the current retrieval core.

## Motivation

Recent comparison against fast-context showed CST is strong for exact keywords and symbol-heavy searches, but weak when the user asks in Chinese for concepts named in English code. The clearest failure was:

```text
数据看板统计图表功能
```

CST with hash and BGE-M3 failed to surface Dashboard-related code, while fast-context found `DashboardController`, `DashboardService`, and `DashboardServiceImpl`. The root gap is not just embedding quality. The query needs a planning step that can bridge terms such as:

```text
看板 -> dashboard
统计 -> statistics
图表 -> chart
权限 -> permission, auth, access
开门 -> open door, openDoor
```

The first planner should target this gap directly while preserving local/offline operation.

## Goals

- Improve cross-language and business-term retrieval by expanding user queries before retrieval.
- Use local Ollama model `qwen3.5:4b-mlx` as the first LLM planner backend.
- Keep planner output structured, bounded, and easy to validate.
- Preserve the current retrieval contract when the planner is disabled or unavailable.
- Keep all existing CLI and MCP query paths on the same core retrieval API.
- Record planner input/output in MCP feedback logs for later evaluation.
- Provide deterministic fallback behavior when the planner fails, times out, or returns invalid JSON.

## Non-Goals

- No LLM reranking in this milestone.
- No LLM answer generation.
- No autonomous multi-turn agent loop.
- No remote model provider in the first implementation.
- No new vector store or embedding model change.
- No change to index format or manifest compatibility.
- No broad Java-specific hard-coding in the core.
- No claim of fast-context parity.

## User Experience

The default behavior remains unchanged.

```toml
[query_planner]
enabled = false
provider = "ollama"
model = "qwen3.5:4b-mlx"
base_url = "http://localhost:11434"
timeout_seconds = 8
max_rewritten_queries = 4
max_keywords = 12
max_symbol_hints = 8
```

When enabled, `cst query` still accepts the same arguments:

```text
cst query <repo> "数据看板统计图表功能"
cst query <repo> "数据看板统计图表功能" --json
```

The Markdown output should remain focused on ranked code results. Planner details should not dominate human output. JSON output and MCP output should expose planner diagnostics so agents can explain why a query expanded.

Example JSON planner section:

```json
{
  "planner": {
    "enabled": true,
    "provider": "ollama",
    "model": "qwen3.5:4b-mlx",
    "status": "ok",
    "rewritten_queries": [
      "数据看板 dashboard statistics chart",
      "DashboardController DashboardService StatisticsService"
    ],
    "grep_keywords": ["Dashboard", "Statistics", "Chart"],
    "symbol_hints": ["DashboardController", "DashboardService", "DashboardServiceImpl"],
    "intent": "feature_lookup"
  }
}
```

If the planner fails, output should still return normal retrieval results with planner status recorded as a fallback:

```json
{
  "planner": {
    "enabled": true,
    "provider": "ollama",
    "model": "qwen3.5:4b-mlx",
    "status": "fallback",
    "error": "planner timed out after 8 seconds"
  }
}
```

## Architecture

The query flow becomes:

```text
User Query
  -> Query Planner (optional)
       -> rewritten queries
       -> grep keywords
       -> symbol hints
       -> intent
  -> Query Normalize
  -> Query Expansion
  -> Candidate Retrieval
       -> semantic topK
       -> lexical topK
       -> path/name/symbol topK
       -> signal matches
  -> Relation Expansion
  -> Merge + Dedupe
  -> Rerank
  -> Context Expand
  -> Format Output
```

The planner is a new core component with a small interface:

```python
class QueryPlanner(Protocol):
    def plan(self, query: str, repo_profile: RepoProfile | None = None) -> QueryPlan:
        ...
```

The first implementation can keep `RepoProfile` minimal or omit it from the runtime call if it is not needed. The boundary exists so later versions can pass language mix, top-level package names, common symbols, or previous feedback without changing the planner contract.

## Core Data Model

Planner output should be explicit and bounded.

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
    error: str | None = None
```

Allowed `status` values:

- `disabled`: planner is not enabled.
- `ok`: planner returned valid structured output.
- `fallback`: planner was enabled but failed, timed out, or returned invalid output.

Initial allowed `intent` values:

- `feature_lookup`
- `endpoint_lookup`
- `bug_trace`
- `data_flow`
- `symbol_lookup`
- `unknown`

The retrieval pipeline should treat all planner fields as hints, not facts.

## Planner Prompt Contract

The qwen planner prompt should be short and strict. It should ask for JSON only and include the output schema. The model must not produce prose.

Prompt behavior:

- Keep the original query.
- Add English code terms for Chinese business words.
- Add likely Java/Spring class or method names only when strongly implied.
- Prefer concise keywords over long paraphrases.
- Do not invent file paths.
- Do not include explanations.
- Return valid JSON.

Example system instruction:

```text
You rewrite code-search queries. Return only compact JSON matching the schema.
Do not explain. Do not guess file paths. Prefer identifiers and English code terms.
```

Example user payload:

```json
{
  "query": "数据看板统计图表功能",
  "language_hints": ["Java", "Spring"],
  "max_rewritten_queries": 4,
  "max_keywords": 12,
  "max_symbol_hints": 8
}
```

Expected shape:

```json
{
  "rewritten_queries": [
    "数据看板 dashboard statistics chart",
    "DashboardController DashboardService DashboardServiceImpl"
  ],
  "grep_keywords": ["Dashboard", "Statistics", "Chart"],
  "symbol_hints": ["DashboardController", "DashboardService", "DashboardServiceImpl"],
  "intent": "feature_lookup"
}
```

## Retrieval Integration

The planner should affect recall in three ways:

1. Token expansion:
   - Tokenize the original query.
   - Tokenize each rewritten query.
   - Tokenize grep keywords and symbol hints.
   - Dedupe while preserving original query tokens first.

2. Candidate retrieval:
   - Run the existing semantic/vector search for the original query.
   - Run lexical/path/symbol/signal retrieval with expanded tokens.
   - Optionally run semantic retrieval for each rewritten query in a bounded loop.

3. Ranking reasons:
   - Add a reason such as `planner hint match` when a result is supported only by planner-expanded terms.
   - Keep existing reasons such as `lexical match`, `path/symbol match`, `signal match`, and `relation expansion`.

The original query must keep priority. Planner hints should improve recall without drowning exact matches.

## Configuration

Add a new config section:

```python
@dataclass(frozen=True)
class QueryPlannerConfig:
    enabled: bool = False
    provider: str = "ollama"
    model: str = "qwen3.5:4b-mlx"
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 8.0
    max_rewritten_queries: int = 4
    max_keywords: int = 12
    max_symbol_hints: int = 8
```

`ToolConfig` owns this config:

```python
@dataclass(frozen=True)
class ToolConfig:
    index: IndexConfig = field(default_factory=IndexConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    query_planner: QueryPlannerConfig = field(default_factory=QueryPlannerConfig)
```

This config is query-time behavior. It should not affect index compatibility and should not be written into the manifest.

## Ollama Client Behavior

The Ollama planner should call the local chat API:

```text
POST http://localhost:11434/api/chat
```

Request traits:

- Use `model = "qwen3.5:4b-mlx"`.
- Use `stream = false`.
- Use a short timeout from config.
- Use `requests.Session`.
- Set `trust_env = False` for default sessions so local requests do not route through system proxies.
- Parse only JSON content from the model response.

If the response is not valid JSON, the planner returns `QueryPlan(status="fallback", error=...)`.

## Fallback And Safety

Planner failure must never block retrieval.

Fallback cases:

- Ollama is not running.
- Model is missing.
- Request times out.
- API returns non-2xx.
- Model returns invalid JSON.
- JSON is valid but fields have wrong types.
- Planner returns too many items.

Fallback behavior:

- Return a disabled/fallback `QueryPlan`.
- Continue with original query only.
- Include planner status in JSON/MCP output.
- Avoid printing stack traces in CLI output.

Field limits must be enforced after parsing:

- Drop empty strings.
- Strip whitespace.
- Dedupe case-insensitively where practical.
- Truncate lists to configured limits.
- Ignore unknown intent values and use `unknown`.

## MCP Feedback

MCP query feedback should include planner metadata:

```json
{
  "planner": {
    "enabled": true,
    "provider": "ollama",
    "model": "qwen3.5:4b-mlx",
    "status": "ok",
    "rewritten_queries": ["..."],
    "grep_keywords": ["..."],
    "symbol_hints": ["..."],
    "intent": "feature_lookup"
  }
}
```

Feedback logs should not include prompt text by default. The planned hints are enough for quality analysis and avoid storing unnecessary prompt details.

## Testing Strategy

Unit tests:

- Config rendering includes `[query_planner]`.
- Config loading preserves planner fields.
- Disabled planner returns `status="disabled"`.
- Ollama planner parses valid JSON into `QueryPlan`.
- Ollama planner bypasses environment proxies.
- Ollama planner falls back on timeout, HTTP error, invalid JSON, and wrong field types.
- Planner list cleanup strips, dedupes, and truncates fields.

Retrieval pipeline tests:

- With planner disabled, existing query results are unchanged.
- With a fake planner returning `Dashboard` hints, a Chinese query can retrieve Dashboard fixture files.
- Planner hint matches add a visible reason without removing existing reasons.
- Planner fallback still returns original-query results.

MCP tests:

- Query payload includes planner metadata.
- Feedback log includes planner metadata.
- Feedback does not include full prompt text.

Integration smoke test:

- With `qwen3.5:4b-mlx` available through Ollama, run `operation-admin-api` query for:

```text
数据看板统计图表功能
```

Expected first milestone result:

- `DashboardController`, `DashboardService`, or `DashboardServiceImpl` appears in Top 5.

## Performance Expectations

Planner execution is query-time overhead. The first target is acceptable local development latency, not sub-second response.

Initial budgets:

- Planner timeout: 8 seconds.
- Rewritten queries: at most 4.
- Keywords: at most 12.
- Symbol hints: at most 8.
- Semantic searches for rewritten queries: bounded by `max_rewritten_queries`.

If local qwen latency is high, users can leave the planner disabled and use it only for difficult cross-language queries.

## Risks

- The planner may hallucinate symbols. Mitigation: treat output as hints and rely on existing index evidence.
- Query latency may become too high. Mitigation: disabled by default, bounded timeout, small output limits.
- Invalid JSON may be common with a small local model. Mitigation: strict prompt, robust parser, fallback.
- Planner hints may drown exact matches. Mitigation: preserve original tokens first and keep original query retrieval priority.
- Local Ollama may be unavailable. Mitigation: fallback to current retrieval.

## Open Decisions For The Implementation Plan

- Whether CLI should add `--planner` and `--no-planner` overrides in the first implementation, or rely only on config.
- Whether semantic retrieval should run for every rewritten query in the first implementation, or only lexical/symbol retrieval should use rewritten terms.
- Whether Markdown output should include a short planner line when enabled, or keep planner details JSON/MCP-only.

## Acceptance Criteria

- Existing tests pass with planner disabled.
- Query planner is disabled by default.
- Enabling planner does not require reindexing.
- Planner failure degrades to original query retrieval.
- JSON and MCP outputs include planner status.
- A fake planner test proves Chinese `数据看板统计图表功能` can surface Dashboard fixture code through planner hints.
- A real `qwen3.5:4b-mlx` smoke test against `operation-admin-api` surfaces Dashboard-related code in Top 5.
