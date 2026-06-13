# Core Retrieval Baseline Plan - Review and Recommendations

**Reviewed:** 2026-06-13
**Plan:** [2026-06-13-core-retrieval-baseline.md](./2026-06-13-core-retrieval-baseline.md)
**Status:** ⚠️ Needs Enhancement Before Execution

---

## Executive Summary

The plan is **well-structured and task-decomposed**, with clear acceptance criteria and test-first approach. However, it lacks critical operational safety mechanisms and user experience considerations that could lead to silent failures or confusing behavior in production.

**Recommendation:** Address the 3 critical gaps before starting implementation, and consider the 6 quality enhancements during execution.

---

## 🔴 Critical Gaps (Must Fix Before Implementation)

### 1. Index Version Management and Migration Strategy

**Problem:**
Plan states "require reindexing when signal schema changes" but provides no mechanism to enforce or detect version mismatches.

**Risk:**
Users query with old indexes after upgrading, getting incomplete results without understanding why.

**Solution:**
Add to **Task 3: Persist Signals And Relations In SQLite**

#### Step 1.5: Add Schema Version Table

```sql
CREATE TABLE IF NOT EXISTS index_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

INSERT OR REPLACE INTO index_metadata VALUES
  ('schema_version', '2', strftime('%s', 'now')),
  ('indexed_at', strftime('%s', 'now'), strftime('%s', 'now'));
```

#### Step 4.5: Version Check During Indexing

```python
# In indexer.py
CURRENT_SCHEMA_VERSION = 2

def _check_schema_version(store: SQLiteStore) -> bool:
    existing = store.get_metadata("schema_version")
    if existing and int(existing) < CURRENT_SCHEMA_VERSION:
        logger.warning(
            f"Schema version {existing} is outdated. "
            f"Current version: {CURRENT_SCHEMA_VERSION}. "
            f"Index will be rebuilt."
        )
        return False
    return True
```

#### Add to Task 11 Step 2: Version Check During Query

```python
# In cli.py query command
def query_command(repo_path: Path, query: str):
    store = SQLiteStore(repo_path / ".context-search")
    version = store.get_metadata("schema_version")

    if not version or int(version) < CURRENT_SCHEMA_VERSION:
        console.print(
            "[yellow]Warning:[/yellow] Index was created with an older version. "
            f"Please run: index {repo_path}"
        )
```

**Acceptance Test:**
- Query against v1 index shows warning
- Index command detects v1 schema and rebuilds

---

### 2. Signal Confidence Score Definition

**Problem:**
`CodeRelation.confidence` field exists but has no defined calculation logic or usage.

**Risk:**
Inconsistent confidence values lead to unpredictable ranking; low-quality relations pollute results.

**Solution:**
Add to **Task 6: Java Short-Chain Relation Signals**

#### Step 3.5: Define Confidence Calculation

```python
# In java_plugin.py
def _calculate_relation_confidence(
    kind: str,
    context: dict[str, Any]
) -> float:
    """
    Calculate relation confidence based on extraction context.

    Confidence scale:
    - 1.0: Direct match (implements interface, @Autowired field)
    - 0.8: Strong lexical signal (receiver type + method call)
    - 0.6: Inferred (method name match without type info)
    - 0.4: Weak (name similarity only)
    """
    if kind == "implements":
        return 1.0  # Syntax-guaranteed

    if kind == "calls":
        if context.get("receiver_type_known"):
            return 0.8  # Field type resolved
        elif context.get("method_signature_match"):
            return 0.6  # Signature-based inference
        else:
            return 0.4  # Name-only match

    return 0.5  # Default
```

#### Step 4.5: Add Confidence Filtering to Retrieval

```python
# In retrieval.py
MIN_RELATION_CONFIDENCE = 0.5  # Config constant

def _relation_expansion_candidates(...) -> list[Candidate]:
    relations = store.relations_for_source(signal_id)
    relations = [r for r in relations if r.confidence >= MIN_RELATION_CONFIDENCE]
    # ... rest of expansion logic
```

**Acceptance Test:**
- Low-confidence relations (< 0.5) are filtered during expansion
- High-confidence relations appear in top results

---

### 3. Relation Expansion Depth Limit and Cycle Detection

**Problem:**
Task 7 Step 4 implements relation expansion but doesn't prevent infinite loops or explosion.

**Risk:**
Query hangs or returns thousands of irrelevant candidates in cyclic dependency graphs.

**Solution:**
Add to **Task 7: Multi-Stage Retrieval In Core**

#### Step 4.5: Implement Safe Expansion Logic

```python
# In retrieval.py
MAX_EXPANSION_DEPTH = 3
MAX_EXPANSION_CANDIDATES = 1000

def _relation_expansion_candidates(
    initial_signals: list[CodeSignal],
    store: SQLiteStore,
) -> list[Candidate]:
    """
    Expand through relations with cycle detection and depth limit.
    """
    visited_signals = set()
    candidates = []
    queue = [(sig, 0) for sig in initial_signals]  # (signal, depth)

    while queue and len(candidates) < MAX_EXPANSION_CANDIDATES:
        signal, depth = queue.pop(0)

        if signal.signal_id in visited_signals:
            continue
        visited_signals.add(signal.signal_id)

        if depth >= MAX_EXPANSION_DEPTH:
            continue

        # Get outgoing relations
        relations = store.relations_for_source(signal.signal_id)
        relations = [r for r in relations if r.confidence >= MIN_RELATION_CONFIDENCE]

        # Find target signals
        for rel in relations:
            target_signals = store.signals_by_name(rel.target_name)
            for target_sig in target_signals:
                candidates.append(Candidate(
                    chunk_id=target_sig.chunk_id,
                    score=_relation_score(rel, depth),
                    reasons=[f"relation: {rel.kind} from {signal.name}"],
                ))
                queue.append((target_sig, depth + 1))

    if len(candidates) >= MAX_EXPANSION_CANDIDATES:
        logger.warning(
            f"Relation expansion hit limit ({MAX_EXPANSION_CANDIDATES}). "
            "Results may be incomplete."
        )

    return candidates

def _relation_score(relation: CodeRelation, depth: int) -> float:
    """Decay score by depth and confidence."""
    base_score = 0.7  # Below direct matches, above weak lexical
    return base_score * relation.confidence * (0.8 ** depth)
```

**Acceptance Test:**
- Query with cyclic relations (A→B→C→A) terminates
- Expansion stops at depth 3
- Warning logged when hitting candidate limit

---

## 🟡 Quality Enhancements (Should Address During Execution)

### 4. Performance Budget and Benchmarking

**Add to Task 11 Step 4: Benchmark Query Performance**

```bash
# Create benchmark script
pytest tests/test_benchmarks.py -v --benchmark

# Expected results:
# Query latency (P95): < 500ms for typical queries
# Index size overhead: < 30% of source code size
# Signal extraction: < 100ms per Java file
```

**Acceptance Criteria:**
- Workbench query on `irs-portal-base` (5000+ files) completes in < 1s
- Signal tables size < 50MB for 10,000 Java files
- Multi-stage retrieval adds < 200ms vs single-stage

---

### 5. Graceful Degradation Strategy

**Add to Task 7 Step 5.5: Implement Fallback Logic**

```python
# In retrieval.py
def query_repository(
    query: str,
    store: SQLiteStore,
    config: RetrievalConfig,
) -> QueryBundle:
    try:
        # Attempt multi-stage retrieval
        return _multi_stage_retrieval(query, store, config)
    except Exception as e:
        logger.warning(
            f"Multi-stage retrieval failed: {e}. "
            "Falling back to lexical-only search."
        )
        return _lexical_only_retrieval(query, store, config)

def _has_signals(store: SQLiteStore) -> bool:
    """Check if index has signal data."""
    cursor = store.conn.execute(
        "SELECT COUNT(*) FROM code_signals WHERE deleted_at IS NULL"
    )
    return cursor.fetchone()[0] > 0
```

**Scenarios:**
- Signal tables empty → use lexical search only
- Signal query fails → log error, continue without signals
- Relation expansion times out → return partial results

---

### 6. CLI Observability (--explain Flag)

**Add to cli.py query command:**

```python
@app.command()
def query(
    repo_path: Path,
    query: str,
    limit: int = 20,
    explain: bool = typer.Option(False, "--explain", help="Show retrieval stages"),
):
    bundle = query_repository(query, store, config)

    if explain:
        console.print("\n[bold]Retrieval Stages:[/bold]")
        console.print(f"  Lexical matches: {bundle.stats['lexical_count']}")
        console.print(f"  Signal matches: {bundle.stats['signal_count']}")
        console.print(f"  Relation-expanded: {bundle.stats['relation_count']}")
        console.print(f"  Total candidates: {bundle.stats['total_candidates']}")
        console.print(f"  Query time: {bundle.stats['duration_ms']}ms\n")

    # ... rest of output
```

**User Experience:**
```bash
$ query repo "工作台" --explain

Retrieval Stages:
  Lexical matches: 5
  Signal matches: 3 (2 endpoint, 1 comment)
  Relation-expanded: 7 (4 calls, 2 implements, 1 uses)
  Total candidates: 15
  Query time: 287ms

## Summary
### Likely Entry Points
...
```

---

### 7. Signal ID Uniqueness Guarantee

**Problem:** Plan doesn't specify signal ID generation strategy.

**Solution:** Add to Task 2 Step 2

```python
# In models.py
def generate_signal_id(
    file_path: Path,
    kind: str,
    start_line: int,
    name: str,
) -> str:
    """
    Generate deterministic signal ID.
    Format: {file_hash}:{kind}:{line}:{name_hash}
    """
    file_hash = hashlib.sha256(str(file_path).encode()).hexdigest()[:8]
    name_hash = hashlib.sha256(name.encode()).hexdigest()[:8]
    return f"{file_hash}:{kind}:{start_line}:{name_hash}"
```

**Guarantees:**
- Same file + line + kind → same ID (idempotent reindexing)
- Different files/lines → different IDs (no collision)
- ID stable across reindexing (unless file moves)

---

### 8. Signal Conflict Resolution

**Scenario:** Same line has multiple signals (endpoint + comment + usage)

**Solution:** Add to Task 8 Step 2

```python
# Signal priority for grouping (highest first)
SIGNAL_PRIORITY = {
    "endpoint": 10,
    "comment": 5,
    "usage": 3,
    "symbol": 2,
    "type": 1,
}

def _primary_signal(signals: list[CodeSignal]) -> CodeSignal:
    """Select the most representative signal for a chunk."""
    return max(signals, key=lambda s: SIGNAL_PRIORITY.get(s.kind, 0))
```

**Grouping Rule:**
- If chunk has endpoint signal → entry_points
- Else if has usage signal → implementation
- Else if has type signal → related_types

---

### 9. Incremental Indexing Path (Future Work)

**Add to Task 12 README update:**

```markdown
## Limitations

- **Full reindexing required:** Changing a single file requires reindexing the entire repository. Incremental indexing is planned for a future release.
- **No real-time updates:** Index does not automatically refresh when files change. Run `index` command manually after significant changes.

## Roadmap

- [ ] Incremental indexing: `index --file src/App.java`
- [ ] Watch mode: `index --watch` for automatic refresh
- [ ] Signal-only reindex: `index --rebuild-signals` (faster than full reindex)
```

---

## 🟢 Documentation and Developer Experience

### 10. Edge Case Test Coverage

**Add to Task 11 Step 5: Edge Case Smoke Tests**

```python
# tests/test_edge_cases.py

def test_empty_repository(tmp_path: Path):
    """Index succeeds with 0 files."""
    index_repository(tmp_path)
    bundle = query_repository("test", store, config)
    assert bundle.results == []

def test_huge_file(tmp_path: Path):
    """File > 10MB doesn't crash indexer."""
    huge_file = tmp_path / "Huge.java"
    huge_file.write_text("// comment\n" * 1_000_000)
    index_repository(tmp_path)
    # Should succeed without OOM

def test_unicode_paths(tmp_path: Path):
    """Emoji and Chinese file paths work."""
    java_file = tmp_path / "测试😀.java"
    java_file.write_text("class Test {}")
    index_repository(tmp_path)
    bundle = query_repository("Test", store, config)
    assert any("测试😀.java" in r.file_path for r in bundle.results)

def test_corrupted_signal_table(tmp_path: Path):
    """Query degrades gracefully if signals corrupted."""
    store.conn.execute("DROP TABLE code_signals")
    bundle = query_repository("test", store, config)
    # Should fall back to lexical search
    assert bundle.results is not None
```

---

### 11. Plugin Development Guide

**Create: `docs/plugin-development.md`**

```markdown
# Plugin Development Guide

## Overview

Plugins extend context-search-tool to support additional languages by extracting language-specific signals.

## Plugin Interface

```python
from context_search_tool.plugins import PluginExtraction, CodeSignal, CodeRelation

def extract_signals(
    file_path: Path,
    content: str,
    chunks: list[ChunkData],
) -> PluginExtraction:
    """
    Extract signals and relations from source code.

    Returns:
        PluginExtraction with:
        - signals: CodeSignal objects (endpoints, comments, usages)
        - relations: CodeRelation objects (calls, implements)
    """
    pass
```

## Signal Types

- `endpoint`: API endpoints (REST, GraphQL, RPC)
- `comment`: Docstrings, inline comments with business context
- `usage`: Method calls, imports, references
- `symbol`: Class/function definitions (lightweight)
- `type`: DTO, enum, interface definitions

## Example: Python Plugin

See [python_plugin.py](../src/context_search_tool/python_plugin.py) for:
- FastAPI/Flask endpoint extraction
- Docstring parsing
- Import statement analysis

## Testing Checklist

- [ ] Plugin works with 0-signal files (plain code)
- [ ] Plugin handles syntax errors gracefully
- [ ] Signals have unique IDs within file
- [ ] Relations reference valid signal IDs
- [ ] Confidence scores are in [0, 1] range
```

---

### 12. Technical Debt Tracking

**Create: `docs/future-work.md`**

```markdown
# Future Work and Known Limitations

## Lightweight Extraction Tradeoffs

The current implementation uses regex-based extraction for speed and simplicity. This has known limitations:

### Java Plugin
- **No full AST parser:** May miss complex generics, lambdas, nested classes
  - TODO(v2): Integrate tree-sitter or javalang for precise parsing
- **No complete call graph:** Only extracts direct method calls in method bodies
  - TODO(v2): Add data-flow analysis for field assignments, constructor calls
- **No MyBatis XML analysis:** SQL queries in XML mappers are not indexed
  - TODO(v3): Parse MyBatis XML and link to mapper interfaces

### Core Retrieval
- **No semantic embedding:** Uses hash-based vectors instead of neural embeddings
  - TODO(v2): Integrate sentence-transformers or instructor-xl
- **No query expansion:** User query is not expanded with synonyms or paraphrases
  - TODO(v2): Add query rewriting with Claude API or local LLM
- **No session context:** Each query is independent
  - TODO(v3): Support conversational refinement

## Known Issues

- Relation expansion may include false positives for common method names (e.g., `save`, `get`)
- Signal extraction is English/Chinese optimized; other languages may need tuning
- No support for monorepos with multiple languages in same directory

## Milestone Roadmap

- **v0.2 (current):** Multi-stage retrieval + Java signals
- **v0.3:** Python plugin + real semantic embeddings
- **v0.4:** TypeScript/JavaScript plugin + incremental indexing
- **v0.5:** Go plugin + MCP server integration
```

---

## Recommended Execution Order

1. **Before Task 1:** Add schema version table (Critical Gap #1)
2. **During Task 6:** Define confidence calculation (Critical Gap #2)
3. **During Task 7:** Add expansion limits and cycle detection (Critical Gap #3)
4. **During Task 11:** Add performance benchmarks (Quality #4)
5. **During Task 11:** Add edge case tests (Documentation #10)
6. **During Task 12:** Add degradation strategy docs (Quality #5)
7. **After Task 12:** Create plugin development guide (Documentation #11)

---

## Priority Matrix

| Item | Impact | Effort | Priority |
|------|--------|--------|----------|
| Index version management | 🔥 High | Low | **P0** |
| Confidence calculation | 🔥 High | Low | **P0** |
| Expansion limits | 🔥 High | Medium | **P0** |
| Performance benchmarks | Medium | Medium | P1 |
| Graceful degradation | Medium | Low | P1 |
| CLI --explain flag | Low | Low | P2 |
| Edge case tests | Medium | Medium | P2 |
| Plugin dev guide | Low | Medium | P3 |

---

## Approval Checklist

Before proceeding with implementation:

- [ ] Acknowledge index version management requirement
- [ ] Agree on confidence score definition
- [ ] Confirm expansion depth limit (default: 3)
- [ ] Decide on performance budget targets
- [ ] Review degradation strategy approach

---

## Questions for Plan Author

1. **Schema Migration:** Should v1 indexes auto-upgrade or require full rebuild?
2. **Confidence Tuning:** Should confidence threshold be user-configurable via CLI flag?
3. **Expansion Strategy:** Should expansion depth be query-dependent (shallow for broad queries, deep for specific)?
4. **Performance:** What is the acceptable query latency for a 10,000-file repository?
5. **Observability:** Should --explain be default-on during milestone validation?

---

**Reviewers:** Claude Code (Opus 4.8)
**Review Date:** 2026-06-13
**Next Step:** Address P0 items before starting Task 1
