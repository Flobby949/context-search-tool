# Core Retrieval Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the core retrieval baseline from single-pass hybrid search into multi-stage, signal-aware retrieval, with Java as the first signal producer used to validate the core design.

**Architecture:** Keep the existing CLI, index location, chunking, SQLite, FTS, and vector-store foundations. Add a language-neutral signal layer to the core, persist those signals in SQLite, use them during a second retrieval stage, and let the Java plugin emit Spring endpoint, comment, usage, and short-chain relation signals without hard-coding Java behavior into core ranking.

**Tech Stack:** Python 3.11+, Typer, SQLite FTS5, NumPy, dataclasses, pytest, existing Java fixture tests.

---

## Context

The current MVP already has a usable local retrieval baseline:

- Source scanning and `.context-search/` index layout.
- Chunking and Java symbol extraction.
- SQLite FTS, token search, symbol/path search.
- Hash embedding through `HashEmbeddingProvider`.
- NumPy vector storage.
- Markdown and JSON output.

Recent comparisons against fast-context showed the current baseline can find relevant files, but it does not reliably turn a business query into:

```text
entry point -> implementation -> related DTO/enum -> possibly legacy code
```

The next milestone should improve the core baseline, not optimize for one target repository. Java is only the first plugin that produces richer signals for the core to consume.

## Assumptions

- Keep `.context-search/` as the target repository index directory.
- Keep `hash-v1` as the default embedding provider for this milestone.
- Require reindexing when signal schema changes; enforce this with stored index metadata and a query-time stale-index warning. Backward-compatible migration is not required for this milestone.
- Use fixed safety defaults for the first retrieval baseline: relation confidence threshold `0.5`, maximum relation expansion depth `3`, and maximum relation-expanded candidates `1000`.
- Do not add MCP, interactive mode, LLM reranking, or a real local embedding model in this milestone.
- Do not build a complete Java AST or full call graph.
- Treat Java/Spring as the first validation plugin, not as core behavior.
- Preserve current README and `.gitignore` edits unless an implementation task explicitly updates docs.

## Scope

In scope:

- Vector search numeric stability.
- Core signal and relation models.
- SQLite persistence for signals and relations.
- Java plugin endpoint, comment, usage, and short-chain relation extraction.
- Multi-stage retrieval with signal expansion.
- Result grouping and summary output.
- Fixture-based acceptance tests.
- Real-repository smoke checks against `irs-portal-base`.

Out of scope:

- Real semantic embedding model selection.
- Long-range call graph analysis.
- MyBatis XML deep parsing.
- Language-server integration.
- Background indexing.
- Query sessions or interactive refinement.

## File Map

- Modify `src/context_search_tool/models.py`
  - Add language-neutral signal, relation, grouped result, and summary dataclasses.
- Modify `src/context_search_tool/plugins.py`
  - Extend plugin extraction results so plugins can return signals and relations.
- Modify `src/context_search_tool/java_plugin.py`
  - Emit Spring endpoint signals, Java comment signals, usage signals, and short-chain relation candidates.
- Modify `src/context_search_tool/sqlite_store.py`
  - Persist signals and relations, retrieve them by chunk, token, and relation endpoint.
- Modify `src/context_search_tool/indexer.py`
  - Store plugin-produced signals and relations during indexing, and rebuild stale indexes when the stored signal schema version is older.
- Modify `src/context_search_tool/cli.py`
  - Warn before query output when the existing index is missing or older than the current signal schema version.
- Modify `src/context_search_tool/retrieval.py`
  - Split retrieval into initial retrieval, signal expansion, relation expansion, reranking, and grouping.
- Modify `src/context_search_tool/vector_store.py`
  - Make vector normalization and scoring robust against non-finite values.
- Modify `src/context_search_tool/formatters.py`
  - Add Markdown and JSON summary sections while keeping existing result detail output.
- Modify tests under `tests/`
  - Add focused tests for each new behavior.
- Modify fixture under `tests/fixtures/java-spring-mini/`
  - Add a Spring controller/service/implementation/executor/DTO fixture that exercises the core baseline.

---

### Task 1: Stabilize Vector Search

**Files:**
- Modify: `src/context_search_tool/vector_store.py`
- Test: `tests/test_embeddings_vector_store.py`

- [ ] **Step 1: Write failing vector stability tests**

Add tests that cover zero vectors, vectors containing `inf`, vectors containing `nan`, and query vectors containing `nan`.

Expected behavior:

- Search returns deterministic results.
- Non-finite vector values are treated as zero during normalization.
- No NumPy runtime warnings are emitted.

Suggested test cases:

```python
def test_vector_search_sanitizes_non_finite_values(tmp_path: Path) -> None:
    store = NumpyVectorStore(tmp_path)
    store.upsert_many(
        [
            ("finite", np.asarray([1.0, 0.0], dtype=np.float32)),
            ("nan", np.asarray([np.nan, 1.0], dtype=np.float32)),
            ("inf", np.asarray([np.inf, 1.0], dtype=np.float32)),
        ]
    )

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        results = store.search(np.asarray([1.0, np.nan], dtype=np.float32), 3, set())

    assert captured == []
    assert [result.chunk_id for result in results] == ["finite", "inf", "nan"]
    assert all(math.isfinite(result.score) for result in results)
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
pytest tests/test_embeddings_vector_store.py -v
```

Expected: new test fails before implementation.

- [ ] **Step 3: Implement vector sanitization**

Update `vector_store.py` so `_normalize_vector` and `_normalize_matrix` call `np.nan_to_num` before norm calculation and matrix multiplication.

Implementation rule:

- `nan`, `inf`, and `-inf` become `0.0`.
- Zero vectors remain zero vectors.
- Search never returns non-finite scores.

- [ ] **Step 4: Verify**

Run:

```bash
pytest tests/test_embeddings_vector_store.py -v
```

Expected: all vector-store tests pass.

---

### Task 2: Add Core Signal And Relation Models

**Files:**
- Modify: `src/context_search_tool/models.py`
- Modify: `src/context_search_tool/plugins.py`
- Test: `tests/test_chunker_java_plugin.py`
- Test: `tests/test_sqlite_store.py`

- [ ] **Step 1: Add model tests**

Add tests that construct these model objects and assert their fields are stable:

```python
CodeSignal(
    signal_id="sig-1",
    chunk_id="chunk-1",
    file_path=Path("src/App.java"),
    kind="endpoint",
    name="GET /apply/audit/stats/wait",
    start_line=10,
    end_line=15,
    language="java",
    tokens=["apply", "audit", "stats", "wait"],
    metadata={"http_method": "GET", "path": "/apply/audit/stats/wait"},
)

CodeRelation(
    relation_id="rel-1",
    source_signal_id="sig-controller",
    target_name="ResourceAuditService.statsWait",
    kind="calls",
    confidence=0.8,
    metadata={"reason": "controller method body call"},
)
```

Expected model fields:

- `CodeSignal.kind` supports at least `endpoint`, `comment`, `symbol`, `usage`, and `type`.
- `CodeRelation.kind` supports at least `calls`, `implements`, `uses`, and `returns`.
- `CodeRelation.confidence` is a `0.0` to `1.0` score where `1.0` means syntax-guaranteed and lower scores mean increasingly inferred.
- Models remain language-neutral.

- [ ] **Step 2: Add deterministic ID helpers**

Add helpers in `models.py` so plugin-produced signals and relations have stable IDs across reindexing:

```python
generate_signal_id(
    file_path=Path("src/App.java"),
    kind="endpoint",
    start_line=10,
    name="GET /apply/audit/stats/wait",
)

generate_relation_id(
    source_signal_id="sig-controller",
    target_name="ResourceAuditService.statsWait",
    kind="calls",
)
```

Expected behavior:

- same file, kind, start line, and signal name produces the same signal id
- different file paths or line numbers produce different signal ids
- same source signal, target name, and relation kind produces the same relation id
- generated ids are short, deterministic strings safe to store as SQLite primary keys

- [ ] **Step 3: Extend plugin extraction contract**

Update `PluginExtraction` so it can return:

```python
signals: list[CodeSignal]
relations: list[CodeRelation]
```

Default these fields to empty lists so existing plugins and tests continue to work.

- [ ] **Step 4: Verify current Java plugin tests still pass**

Run:

```bash
pytest tests/test_chunker_java_plugin.py tests/test_sqlite_store.py -v
```

Expected: existing behavior remains green after the contract extension.

---

### Task 3: Persist Signals And Relations In SQLite

**Files:**
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/indexer.py`
- Modify: `src/context_search_tool/cli.py`
- Test: `tests/test_sqlite_store.py`
- Test: `tests/test_indexer_manifest.py`
- Test: `tests/test_cli_commands.py`

- [ ] **Step 1: Write store tests for signals**

Add a test that initializes a store, inserts one chunk plus two signals, and reads them back by chunk id and token.

Expected APIs:

```python
store.replace_chunks(file_path, chunks)
store.replace_signals(file_path, signals)
store.signals_for_chunk("chunk-1")
store.signal_search(["stats", "wait"], limit=10)
```

- [ ] **Step 2: Write store tests for relations**

Add a test that inserts a `calls` relation and reads it by source signal id and by target name.

Expected APIs:

```python
store.replace_relations(file_path, relations)
store.relations_for_source("sig-controller")
store.relations_targeting("ResourceAuditService.statsWait")
```

- [ ] **Step 3: Write metadata and stale-index tests**

Add tests for index metadata storage and stale schema handling.

Expected APIs and behavior:

```python
store.set_metadata("signal_schema_version", "2")
assert store.get_metadata("signal_schema_version") == "2"
```

- indexing an index with `signal_schema_version="1"` clears stale signal and relation rows before writing new rows
- querying an index with no `signal_schema_version` or an older version prints a warning that tells the user to rerun `index`

- [ ] **Step 4: Implement schema**

Add tables:

```sql
CREATE TABLE IF NOT EXISTS index_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS code_signals (
  signal_id TEXT PRIMARY KEY,
  chunk_id TEXT NOT NULL,
  file_path TEXT NOT NULL,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  language TEXT NOT NULL,
  tokens TEXT NOT NULL,
  metadata TEXT NOT NULL,
  deleted_at INTEGER
);

CREATE TABLE IF NOT EXISTS code_relations (
  relation_id TEXT PRIMARY KEY,
  source_signal_id TEXT NOT NULL,
  source_chunk_id TEXT NOT NULL,
  source_file_path TEXT NOT NULL,
  target_name TEXT NOT NULL,
  kind TEXT NOT NULL,
  confidence REAL NOT NULL,
  metadata TEXT NOT NULL,
  deleted_at INTEGER
);
```

Add indexes for:

- active signal by chunk id
- active signal by file path
- active relation by source signal id
- active relation by target name

- [ ] **Step 5: Wire indexer persistence and schema version checks**

During indexing:

- Define a single current signal schema constant, for example `CURRENT_SIGNAL_SCHEMA_VERSION = 2`.
- Read `signal_schema_version` from `index_metadata` before writing signal data.
- If the stored version is missing or older than the current version, remove stale signal and relation data before continuing. A full chunk/vector rebuild is acceptable for this milestone if it is simpler than partial cleanup.
- Continue storing chunks, symbols, tokens, and vectors as before.
- Store plugin-produced signals and relations for the indexed file.
- Mark prior active signals and relations for the file as deleted before inserting replacement rows.
- Write `signal_schema_version` and `indexed_at` metadata after a successful index run.

- [ ] **Step 6: Add query-time stale-index warning**

Before running a query in `cli.py`, read `signal_schema_version` from the repository index. If it is missing or older than `CURRENT_SIGNAL_SCHEMA_VERSION`, print a warning and continue with the best available lexical/vector results.

Expected warning:

```text
Warning: index signal schema is older than this version. Run index again for signal-aware retrieval.
```

- [ ] **Step 7: Verify**

Run:

```bash
pytest tests/test_sqlite_store.py tests/test_indexer_manifest.py tests/test_cli_commands.py -v
```

Expected: tests pass.

---

### Task 4: Java Spring Endpoint Signals

**Files:**
- Modify: `src/context_search_tool/java_plugin.py`
- Modify fixture: `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/ApplyAuditController.java`
- Test: `tests/test_chunker_java_plugin.py`
- Test: `tests/test_acceptance_java_fixture.py`

- [ ] **Step 1: Extend fixture controller**

Add methods with representative mappings:

```java
@RestController
@RequestMapping("/apply/audit")
public class ApplyAuditController {
    private final ResourceAuditService resourceAuditService;

    /**
     * 工作台统计-待我审核
     */
    @GetMapping("/stats/wait")
    public Map<String, Long> statsWait() {
        return resourceAuditService.statsWait();
    }

    /**
     * 工作台统计-审核列表
     */
    @PostMapping("/stats")
    public WorkbenchResourceAuditStatsDTO auditStats(@RequestBody ApplyAuditEsSearchQry qry) {
        return resourceAuditService.auditStats(qry);
    }
}
```

- [ ] **Step 2: Write endpoint extraction tests**

Assert the Java plugin emits endpoint signals:

- `GET /apply/audit/stats/wait`
- `POST /apply/audit/stats`

Each endpoint signal must include:

- `kind="endpoint"`
- `metadata["http_method"]`
- `metadata["path"]`
- `metadata["controller"]`
- `metadata["method"]`
- nearby JavaDoc/comment text tokens

- [ ] **Step 3: Implement endpoint extraction**

Extend existing mapping extraction so it creates `CodeSignal` objects rather than only adding lexical route tokens.

Implementation rules:

- Class-level `@RequestMapping` is joined with method-level mapping.
- `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, and `@PatchMapping` set HTTP method directly.
- `@RequestMapping(method = RequestMethod.POST)` is supported if straightforward to extract.
- Empty mapping path is allowed and joins to the class path.

- [ ] **Step 4: Verify**

Run:

```bash
pytest tests/test_chunker_java_plugin.py tests/test_acceptance_java_fixture.py -v
```

Expected: endpoint signal tests pass.

---

### Task 5: Java Comment And Usage Signals

**Files:**
- Modify: `src/context_search_tool/java_plugin.py`
- Test: `tests/test_chunker_java_plugin.py`

- [ ] **Step 1: Write comment signal tests**

Use a Java fixture method with Chinese JavaDoc and assert:

- comment text is preserved in a `comment` signal
- Chinese business terms are tokenized enough to match query text
- the comment signal is linked to the nearest method or type through metadata

Example expectations:

```python
assert "工作台统计" in comment_signal.metadata["text"]
assert comment_signal.metadata["owner_method"] == "statsWait"
```

- [ ] **Step 2: Write usage signal tests**

For a controller method body:

```java
return resourceAuditService.statsWait();
```

Assert a `usage` signal is emitted with:

- `name="resourceAuditService.statsWait"`
- `metadata["receiver"] == "resourceAuditService"`
- `metadata["method"] == "statsWait"`
- `metadata["owner_method"] == "statsWait"`

- [ ] **Step 3: Implement comment extraction**

Add lightweight extraction for:

- JavaDoc blocks immediately before class/method declarations.
- `//` comments immediately before class/method declarations.

Do not build a full comment parser. Keep this local and line-based.

- [ ] **Step 4: Implement usage extraction**

Add lightweight method-call extraction inside method bodies:

- Match `receiver.methodName(`.
- Skip common keywords such as `if`, `for`, `while`, `switch`, `return`, and `new`.
- Limit extraction to the current method body using brace depth.

- [ ] **Step 5: Verify**

Run:

```bash
pytest tests/test_chunker_java_plugin.py -v
```

Expected: comment and usage signal tests pass.

---

### Task 6: Java Short-Chain Relation Signals

**Files:**
- Modify fixture under `tests/fixtures/java-spring-mini/src/main/java/com/example/audit/`
- Modify: `src/context_search_tool/java_plugin.py`
- Test: `tests/test_chunker_java_plugin.py`
- Test: `tests/test_acceptance_java_fixture.py`

- [ ] **Step 1: Extend fixture service chain**

Add or update:

```java
public interface ResourceAuditService {
    Map<String, Long> statsWait();
    WorkbenchResourceAuditStatsDTO auditStats(ApplyAuditEsSearchQry qry);
}

@Service
public class ResourceAuditServiceImpl implements ResourceAuditService {
    private final EsApplyAuditPageQryExe esApplyAuditPageQryExe;

    @Override
    public Map<String, Long> statsWait() {
        return esApplyAuditPageQryExe.statsWait();
    }

    @Override
    public WorkbenchResourceAuditStatsDTO auditStats(ApplyAuditEsSearchQry qry) {
        return esApplyAuditPageQryExe.auditStats(qry);
    }
}
```

- [ ] **Step 2: Write relation tests**

Assert Java plugin emits relation candidates:

- controller endpoint signal `calls` `ResourceAuditService.statsWait`
- implementation type signal `implements` `ResourceAuditService`
- implementation method signal `uses` `EsApplyAuditPageQryExe.statsWait`
- relation confidence scores are deterministic and within the expected confidence scale:
  - `implements`: `1.0`
  - `calls` with known receiver type: `0.8`
  - inferred method/signature match without receiver type: `0.6`
  - name-only relation candidate: `0.4`

- [ ] **Step 3: Implement relation extraction**

Implement lightweight relation extraction:

- Field declarations map receiver variable to type.
- Constructor parameters assigned to fields map receiver variable to type.
- `implements InterfaceName` creates an `implements` relation.
- `receiver.methodName()` creates a `calls` relation targeting `ReceiverType.methodName` when receiver type is known.
- Calculate relation confidence in one helper so all relation producers use the same scale.

- [ ] **Step 4: Verify**

Run:

```bash
pytest tests/test_chunker_java_plugin.py tests/test_acceptance_java_fixture.py -v
```

Expected: short-chain relation tests pass.

---

### Task 7: Multi-Stage Retrieval In Core

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Test: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Write retrieval expansion tests**

Create a test index where:

- initial query matches an endpoint comment signal
- endpoint relation targets a service method
- service method relation targets an executor method

Query:

```text
工作台相关代码
```

Expected result ordering:

1. controller endpoint chunk
2. service implementation chunk
3. executor/query chunk
4. DTO chunk

- [ ] **Step 2: Add explicit retrieval stages**

Refactor `query_repository` into internal stages:

```python
initial_candidates = _initial_candidates(...)
signal_candidates = _signal_candidates(...)
expanded_candidates = _relation_expansion_candidates(...)
merged = _merge_candidates([...])
ranked = _rank_chunks(...)
grouped = _group_results(...)
```

Keep public `query_repository(...)` unchanged.

- [ ] **Step 3: Implement signal candidate retrieval**

Add candidate generation from signal matches:

- signal name match
- signal token match
- signal metadata text match
- endpoint path token match

Use bounded limits from existing retrieval config. Do not add new config fields in this task.

- [ ] **Step 4: Implement relation expansion**

From top initial or signal candidates:

- load signals for those chunks
- load outgoing relations
- ignore relations with confidence below `0.5`
- find active signals/chunks whose symbol or signal name matches relation target
- add those chunks as relation-expanded candidates

Score relation-expanded candidates below direct endpoint matches but above weak lexical-only matches.

- [ ] **Step 5: Add expansion safety limits**

Implement relation expansion with:

- `MAX_EXPANSION_DEPTH = 3`
- `MAX_EXPANSION_CANDIDATES = 1000`
- a visited signal set so cycles such as `A -> B -> C -> A` terminate
- depth-based score decay, for example `base_score * relation.confidence * (0.8 ** depth)`
- a warning log when expansion hits the candidate limit

Add tests that prove:

- cyclic relations terminate
- expansion stops at depth `3`
- low-confidence relations below `0.5` are filtered
- hitting the candidate limit logs a warning and returns partial candidates

- [ ] **Step 6: Verify**

Run:

```bash
pytest tests/test_retrieval_pipeline.py -v
```

Expected: multi-stage retrieval tests pass and existing retrieval tests remain green.

---

### Task 8: Result Grouping And Summary Models

**Files:**
- Modify: `src/context_search_tool/models.py`
- Modify: `src/context_search_tool/retrieval.py`
- Test: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add summary model tests**

Expected new bundle shape:

```python
QueryBundle(
    query="工作台相关代码",
    expanded_tokens=[...],
    summary=RetrievalSummary(
        entry_points=[...],
        implementation=[...],
        related_types=[...],
        possibly_legacy=[...],
    ),
    results=[...],
    followup_keywords=[...],
)
```

Existing callers should continue to work if they only read `bundle.results`.

- [ ] **Step 2: Implement grouping rules**

Rules:

- `entry_points`: endpoint signals and controller chunks.
- `implementation`: service, executor, gateway, mapper, or relation-expanded implementation chunks.
- `related_types`: DTO, enum, request, response, query type, and domain type chunks.
- `possibly_legacy`: chunks that match DTO/type names but have no endpoint, usage, or relation support.

Keep grouping deterministic and explainable.

- [ ] **Step 3: Add reasons**

Add group-related reasons to result reasons:

- `endpoint signal match`
- `comment signal match`
- `relation expansion`
- `implementation chain match`
- `possibly legacy: no active usage signal found`

- [ ] **Step 4: Verify**

Run:

```bash
pytest tests/test_retrieval_pipeline.py -v
```

Expected: summary grouping and existing ranking tests pass.

---

### Task 9: Formatter Summary Output

**Files:**
- Modify: `src/context_search_tool/formatters.py`
- Test: `tests/test_formatters.py`

- [ ] **Step 1: Write Markdown formatter test**

Expected Markdown includes:

```markdown
## Summary

### Likely Entry Points
- GET /apply/audit/stats/wait -> ResourceAuditController.statsWait

### Likely Implementation
- ResourceAuditServiceImpl.statsWait

### Related Types
- WorkbenchResourceAuditStatsDTO

### Possibly Legacy
- WorkbenchResourceStatsDTO
```

The existing `## Results` section must remain.

- [ ] **Step 2: Write JSON formatter test**

Expected JSON includes:

```json
{
  "summary": {
    "entry_points": [],
    "implementation": [],
    "related_types": [],
    "possibly_legacy": []
  },
  "results": []
}
```

- [ ] **Step 3: Implement formatter changes**

Add summary rendering before detailed results.

Rules:

- Omit empty summary groups in Markdown or render `- (none)` consistently.
- Always include all summary keys in JSON.
- Preserve existing JSON keys for compatibility.

- [ ] **Step 4: Verify**

Run:

```bash
pytest tests/test_formatters.py -v
```

Expected: formatter tests pass.

---

### Task 10: Acceptance Tests For Core Baseline

**Files:**
- Modify: `tests/test_acceptance_java_fixture.py`
- Modify fixture under `tests/fixtures/java-spring-mini/`

- [ ] **Step 1: Add acceptance query for workbench-like code**

Index the fixture and query:

```text
工作台相关代码
```

Expected:

- top summary entry point contains `GET /apply/audit/stats/wait`
- implementation summary contains `ResourceAuditServiceImpl.statsWait`
- related types contains `WorkbenchResourceAuditStatsDTO`
- possibly legacy contains `WorkbenchResourceStatsDTO` if it is present in the fixture without usage

- [ ] **Step 2: Add acceptance query for workflow-like interface code**

Add a mini open-process controller fixture and query:

```text
apaas工作流相关接口
```

Expected:

- entry points contain process controller endpoints
- implementation contains process command or gateway-like class
- related types contain request/response DTOs

- [ ] **Step 3: Verify**

Run:

```bash
pytest tests/test_acceptance_java_fixture.py -v
```

Expected: all acceptance tests pass.

---

### Task 11: Full Test And Real Repo Smoke

**Files:**
- No source changes expected unless tests reveal defects.

- [ ] **Step 1: Run full test suite**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Reindex a real Java repository**

Run:

```bash
env PYTHONPATH=src /private/tmp/context-search-tool-venv/bin/python -m context_search_tool.cli index /Users/flobby/work/code/irs-portal-base
```

Expected:

- indexing succeeds
- `.context-search/` is updated in the target repository
- stats show non-zero signals and relations if stats are extended in this milestone

- [ ] **Step 3: Query real repository smoke cases**

Run:

```bash
env PYTHONPATH=src /private/tmp/context-search-tool-venv/bin/python -m context_search_tool.cli query /Users/flobby/work/code/irs-portal-base "工作台相关代码"
env PYTHONPATH=src /private/tmp/context-search-tool-venv/bin/python -m context_search_tool.cli query /Users/flobby/work/code/irs-portal-base "apaas工作流相关接口"
env PYTHONPATH=src /private/tmp/context-search-tool-venv/bin/python -m context_search_tool.cli query /Users/flobby/work/code/irs-portal-base "待我审批 工作台统计 是怎么查的"
```

Expected:

- workbench query surfaces entry endpoints before weak DTO-only matches
- workflow query surfaces process/open-process endpoints and implementation chain
- "待我审批" query surfaces the query-type implementation path
- no NumPy runtime warnings appear

---

### Task 12: Documentation Update

**Files:**
- Modify: `README.md`
- Test: `git diff --check`

- [ ] **Step 1: Update README capability section**

Document the milestone as:

- Core multi-stage retrieval.
- Core signal and relation model.
- Java as the first signal producer.
- Summary output groups.
- Limitations: no complete Java call graph and no real semantic embedding by default.

- [ ] **Step 2: Verify formatting**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

---

## Milestone Acceptance Criteria

The milestone is complete when all of the following are true:

- Full test suite passes with `pytest -q`.
- Vector search emits no runtime warnings for zero or non-finite vectors.
- Java fixture indexes endpoint, comment, usage, and relation signals.
- Retrieval uses direct matches plus signal/relation expansion.
- Markdown output includes a summary before detailed snippets.
- JSON output includes a stable `summary` object.
- Real-repo smoke query `工作台相关代码` returns entry points and implementation before weak DTO-only matches.
- Real-repo smoke query `apaas工作流相关接口` returns endpoint and implementation-chain context.
- No target-repository specific words are hard-coded into core retrieval logic.

## Risks And Stop Conditions

Stop and ask before implementation continues if:

- Signal persistence requires a schema migration strategy more complex than reindexing.
- Java relation extraction requires a real parser dependency.
- Multi-stage retrieval adds too much noise and needs a new config knob.
- Real-repo smoke tests disagree with fixture tests in a way that changes the architecture.
- README or existing uncommitted edits conflict with implementation changes.

## Execution Handoff

After this plan is approved, implementation should proceed task by task. Recommended execution mode:

1. Subagent-driven development for independent tasks such as vector stability, SQLite signal storage, Java extraction, formatter output, and fixture acceptance.
2. Main-agent review after each task to keep the core/plugin boundary clean.
3. Verification-before-completion before reporting the milestone complete.
